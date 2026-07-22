"""链路分析器 - 关联请求/响应并生成统计"""

from typing import Dict, List, Optional, Tuple

from .models import (
    AnalysisResult,
    CallStatus,
    IterationTiming,
    LLMChain,
    LLMRequest,
    LLMResponse,
    Statistics,
    SubagentInfo,
    SystemMetrics,
    ToolExecution,
    pair_requests_responses,
)
from .tool_errors import detect_tool_failure


class ChainAnalyzer:
    def __init__(
        self,
        requests: Dict[str, List[LLMRequest]],
        responses: Dict[str, List[LLMResponse]],
        system_metrics: Optional[Dict[Tuple[str, int], List[SystemMetrics]]] = None,
        tool_executions: Optional[List[ToolExecution]] = None,
    ):
        self.requests = requests
        self.responses = responses
        self.system_metrics = system_metrics or {}
        self.tool_executions = tool_executions or []
        self._tool_execution_by_id = {
            execution.tool_call_id: execution for execution in self.tool_executions
        }
        self._all_sessions = set(requests.keys()) | set(responses.keys())
        self._parent_to_task_ids: Dict[str, List[Tuple[str, float]]] = {}
        self._task_id_to_parent: Dict[str, str] = {}

    def analyze(self) -> AnalysisResult:
        result = AnalysisResult()

        # analyze() 可重复调用；关系索引必须从输入重新构建。
        self._parent_to_task_ids.clear()
        self._task_id_to_parent.clear()
        self._match_spawn_calls_to_task_ids()

        parent_sessions = self._identify_parent_sessions()
        subagent_sessions = self._identify_subagent_sessions()

        for session_id in parent_sessions:
            chain = self._build_parent_chain(session_id, subagent_sessions)
            if chain:
                result.sessions[session_id] = chain

        for session_id in subagent_sessions:
            # 新格式：session_id 本身就是唯一标识，直接检查是否在 _task_id_to_parent 中
            if "_subagent_" in session_id or "_fork_agent_" in session_id:
                if session_id in self._task_id_to_parent:
                    continue
            else:
                # 旧格式：检查 task_id 是否在 _task_id_to_parent 中
                task_id = self._extract_task_id_from_session(session_id)
                if task_id and task_id in self._task_id_to_parent:
                    continue
            chain = self._build_standalone_subagent_chain(session_id)
            if chain:
                result.sessions[session_id] = chain

        result.sorted_sessions = sorted(result.sessions.values(), key=lambda c: c.start_time)

        result.statistics = self._compute_statistics(result.sessions)
        result.diagnostics = {
            "completed_calls": result.statistics.completed_calls,
            "incomplete_calls": result.statistics.incomplete_calls,
            "invalid_calls": result.statistics.invalid_calls,
            "measured_tool_calls": len(self._tool_execution_by_id),
        }

        return result

    def _match_spawn_calls_to_task_ids(self) -> None:
        for session_id in sorted(self._all_sessions):
            direct_parent = self._direct_parent_session(session_id)
            if not direct_parent:
                continue

            child_reqs = self.requests.get(session_id, [])
            child_start = child_reqs[0].timestamp if child_reqs else 0
            root_parent = self._find_root_parent(direct_parent)
            children = self._parent_to_task_ids.setdefault(root_parent, [])
            if not any(child_id == session_id for child_id, _ in children):
                children.append((session_id, child_start))
            self._task_id_to_parent[session_id] = direct_parent

    @staticmethod
    def _direct_parent_session(session_id: str) -> Optional[str]:
        """从最后一个 agent 分隔符取得直接父 session。"""
        positions = [
            session_id.rfind(marker)
            for marker in ("_subagent_", "_fork_agent_")
            if marker in session_id
        ]
        if not positions:
            return None
        return session_id[: max(positions)]

    def _find_root_parent(self, session_id: str, _visited: Optional[set] = None) -> str:
        """递归向上找到真正的顶层父 session"""
        if _visited is None:
            _visited = set()
        if session_id in _visited:
            return session_id  # 防止循环
        _visited.add(session_id)

        parent = self._direct_parent_session(session_id)
        if parent:
            return self._find_root_parent(parent, _visited)
        return session_id

    def _identify_parent_sessions(self) -> List[str]:
        return [s for s in self._all_sessions if not self._is_subagent_session(s)]

    def _identify_subagent_sessions(self) -> List[str]:
        return [s for s in self._all_sessions if self._is_subagent_session(s)]

    @staticmethod
    def _is_subagent_session(session_id: str) -> bool:
        """Recognize current nested IDs and the legacy top-level prefixes."""
        return (
            "_subagent_" in session_id
            or "_fork_agent_" in session_id
            or session_id.startswith("subagent_")
            or session_id.startswith("fork_fork_agent_")
        )

    def _resolve_subagent_session(self, task_id: str) -> str:
        """从 task_id 推导 subagent 的 session_id"""
        if "_subagent_" in task_id or "_fork_agent_" in task_id:
            return task_id
        if task_id.startswith("fork_fork_agent_"):
            return task_id
        return f"subagent_{task_id}"

    def _build_parent_chain(
        self, session_id: str, subagent_sessions: List[str]
    ) -> Optional[LLMChain]:
        reqs = self.requests.get(session_id, [])
        resps = self.responses.get(session_id, [])

        if not reqs and not resps:
            return None

        for req in reqs:
            req.source = "parent"
            req.source_label = "Main"

        for resp in resps:
            resp.source = "parent"
            resp.source_label = "Main"

        model_name = reqs[0].model_name if reqs else (resps[0].model_name if resps else "")

        related_subagents = self._find_related_subagents(session_id)

        subagent_infos: List[SubagentInfo] = []
        for task_id, spawn_time in related_subagents:
            subagent_session = self._resolve_subagent_session(task_id)

            if subagent_session in subagent_sessions:
                subagent_reqs = self.requests.get(subagent_session, [])
                subagent_resps = self.responses.get(subagent_session, [])
                sub_start = subagent_reqs[0].timestamp if subagent_reqs else spawn_time
                sub_end = subagent_resps[-1].timestamp if subagent_resps else 0.0

                # 计算嵌套深度和路径
                depth, chain_path, direct_parent = self._compute_subagent_depth(task_id)

                subagent_infos.append(
                    SubagentInfo(
                        task_id=task_id,
                        session_id=subagent_session,
                        start_time=sub_start,
                        end_time=sub_end,
                        depth=depth,
                        parent_session_id=direct_parent,
                        chain_path=chain_path,
                    )
                )

        all_requests: List[LLMRequest] = list(reqs)
        all_responses: List[LLMResponse] = list(resps)

        for task_id, _ in related_subagents:
            subagent_session = self._resolve_subagent_session(task_id)

            # 计算嵌套深度和路径用于显示
            depth, chain_path, direct_parent = self._compute_subagent_depth(task_id)

            if subagent_session in self.requests:
                for req in self.requests[subagent_session]:
                    req.source = "subagent"
                    req.source_label = self._format_chain_label(chain_path)
                    all_requests.append(req)
            if subagent_session in self.responses:
                for resp in self.responses[subagent_session]:
                    resp.source = "subagent"
                    resp.source_label = self._format_chain_label(chain_path)
                    all_responses.append(resp)

        all_requests.sort(key=lambda r: r.timestamp)
        all_responses.sort(key=lambda r: r.timestamp)

        # 计算时间统计
        iteration_timings = self._compute_iteration_timings(all_requests, all_responses)
        total_llm_duration = sum(t.llm_call_duration for t in iteration_timings)
        total_tool_duration = sum(t.tool_processing_duration for t in iteration_timings)
        observed_times = [r.timestamp for r in all_requests] + [r.timestamp for r in all_responses]
        observed_times.extend(
            execution.end_time
            for timing in iteration_timings
            for execution in timing.tool_executions
        )
        start_time = min(observed_times) if observed_times else 0
        end_time = max(observed_times) if observed_times else 0

        return LLMChain(
            session_id=session_id,
            model_name=model_name,
            requests=all_requests,
            responses=all_responses,
            start_time=start_time,
            end_time=end_time,
            total_iterations=len(iteration_timings),
            subagents=subagent_infos,
            is_subagent=False,
            iteration_timings=iteration_timings,
            total_llm_duration_seconds=total_llm_duration,
            total_tool_duration_seconds=total_tool_duration,
        )

    def _compute_iteration_timings(
        self,
        requests: List[LLMRequest],
        responses: List[LLMResponse],
    ) -> List[IterationTiming]:
        """计算每个迭代的时间统计"""
        timings: List[IterationTiming] = []

        # 新日志按 event_id 配对；旧日志回退 (session_id, iteration)。
        sorted_items = pair_requests_responses(requests, responses)

        for i, item in enumerate(sorted_items, start=1):
            req = item["request"]
            resp = item["response"]

            if not req and not resp:
                continue

            timing = IterationTiming(
                iteration_num=i,
                session_id=req.session_id if req else (resp.session_id if resp else ""),
                request_timestamp=req.timestamp if req else 0,
                response_timestamp=resp.timestamp if resp else 0,
                event_id=(req.event_id if req else (resp.event_id if resp else "")),
                call_kind=(req.call_kind if req else (resp.call_kind if resp else "agent")),
            )

            # 添加系统资源指标
            session_id = timing.session_id
            iteration_key = (session_id, timing.iteration_num)
            if iteration_key in self.system_metrics:
                timing.system_metrics = self.system_metrics[iteration_key]

            if req and resp and resp.timestamp >= req.timestamp:
                timing.status = CallStatus.COMPLETE
                timing.llm_call_duration = resp.timestamp - req.timestamp
            elif req and resp:
                timing.status = CallStatus.INVALID
            elif req:
                timing.status = CallStatus.REQUEST_ONLY
            else:
                timing.status = CallStatus.RESPONSE_ONLY

            # 工具耗时只使用 TelemetryRail 的真实生命周期，不再把模型调用间隙推断为工具。
            if resp:
                delegated_names = {"spawn_subagent", "fork_agent", "spawn_fork_agent"}
                for tool_call in resp.tool_calls:
                    tool_call_id = tool_call.get("id", "")
                    execution = self._tool_execution_by_id.get(tool_call_id)
                    if execution:
                        timing.tool_executions.append(execution)
                        if execution.tool_name not in delegated_names:
                            timing.tool_processing_duration += execution.duration_seconds

            timings.append(timing)

        # 线性标记每个 session 的最后一次调用，避免 O(n²) 向后扫描。
        seen_sessions = set()
        for timing in reversed(timings):
            timing.is_last_iteration = timing.session_id not in seen_sessions
            seen_sessions.add(timing.session_id)

        return timings

    @staticmethod
    def _extract_tool_name(tc: Dict) -> str:
        """从 tool call 中提取名称（兼容多种格式）"""
        name = tc.get("name", "") or tc.get("function", {}).get("name", "")
        return str(name) if name else ""

    def _compute_subagent_depth(self, task_id: str) -> Tuple[int, List[str], str]:
        """计算 subAgent 的嵌套深度和调用路径"""
        chain_path = []
        depth = 0

        # 从映射表获取完整的直接 parent（新格式下存储的是完整 session_id）
        direct_parent = self._task_id_to_parent.get(task_id) or ""

        # 添加当前 subAgent 到路径末尾
        current_short_name = self._short_task_id(task_id)
        if "_fork_agent_" in task_id:
            chain_path.append(f"Fork[{current_short_name}]")
        else:
            chain_path.append(f"Sub[{current_short_name}]")

        current_task_id = task_id
        while True:
            # 从映射表获取 parent
            parent_session = self._task_id_to_parent.get(current_task_id)

            if not parent_session:
                chain_path.insert(0, "Main")
                break

            # 检查 parent 是否也是 subAgent（新格式）
            if "_subagent_" in parent_session or "_fork_agent_" in parent_session:
                short_name = self._short_task_id(parent_session)
                if "_fork_agent_" in parent_session:
                    chain_path.insert(0, f"Fork[{short_name}]")
                else:
                    chain_path.insert(0, f"Sub[{short_name}]")
                depth += 1
                current_task_id = parent_session
                continue

            # 旧格式判断
            if parent_session.startswith("subagent_subagent_"):
                parent_task_id = parent_session[len("subagent_") :]
                short_name = self._short_task_id(parent_task_id)
                chain_path.insert(0, f"Sub[{short_name}]")
                depth += 1
                current_task_id = parent_task_id
            elif parent_session.startswith("fork_fork_agent_"):
                short_name = self._short_task_id(parent_session)
                chain_path.insert(0, f"Fork[{short_name}]")
                depth += 1
                current_task_id = parent_session
            else:
                # 父是顶层 session
                chain_path.insert(0, "Main")
                break

        return depth, chain_path, direct_parent

    def _format_chain_label(self, chain_path: List[str]) -> str:
        """格式化调用链标签"""
        return " → ".join(chain_path)

    def _build_standalone_subagent_chain(self, session_id: str) -> Optional[LLMChain]:
        reqs = self.requests.get(session_id, [])
        resps = self.responses.get(session_id, [])

        if not reqs and not resps:
            return None

        for req in reqs:
            req.source = "subagent"
            req.source_label = "Subagent"

        for resp in resps:
            resp.source = "subagent"
            resp.source_label = "Subagent"

        model_name = reqs[0].model_name if reqs else (resps[0].model_name if resps else "")

        iteration_timings = self._compute_iteration_timings(reqs, resps)
        observed_times = [r.timestamp for r in reqs] + [r.timestamp for r in resps]
        observed_times.extend(
            execution.end_time
            for timing in iteration_timings
            for execution in timing.tool_executions
        )
        return LLMChain(
            session_id=session_id,
            model_name=model_name,
            requests=reqs,
            responses=resps,
            start_time=min(observed_times) if observed_times else 0,
            end_time=max(observed_times) if observed_times else 0,
            total_iterations=len(iteration_timings),
            is_subagent=True,
            iteration_timings=iteration_timings,
            total_llm_duration_seconds=sum(t.llm_call_duration for t in iteration_timings),
            total_tool_duration_seconds=sum(t.tool_processing_duration for t in iteration_timings),
        )

    def _find_related_subagents(self, parent_session: str) -> List[Tuple[str, float]]:
        task_ids = self._parent_to_task_ids.get(parent_session, [])
        return sorted(task_ids, key=lambda x: x[1])

    def _short_task_id(self, task_id: str) -> str:
        if not task_id:
            return "unknown"
        # 优先检查 _fork_agent_（因为 fork_agent session_id 中可能包含 _subagent_）
        # 例如：xxx_subagent_a57b9eed_fork_agent_35121a76 应取 35121a76
        if "_fork_agent_" in task_id:
            parts = task_id.split("_fork_agent_")
            if len(parts) >= 2:
                return parts[-1][:12]
        # 新格式：<parent>_subagent_<task_id>
        if "_subagent_" in task_id:
            parts = task_id.split("_subagent_")
            if len(parts) >= 2:
                return parts[-1][:12]
        # 旧格式 fork_fork_agent_xxxx
        if task_id.startswith("fork_fork_agent_"):
            suffix = task_id[len("fork_fork_agent_") :]
            return f"fork_{suffix[:8]}"
        # 旧格式 subagent_xxxx
        parts = task_id.split("_")
        if len(parts) >= 2:
            return parts[-1][:12]
        return task_id[:12]

    def _extract_task_id_from_session(self, session_id: str) -> Optional[str]:
        # 新格式：<parent>_subagent_<task_id>
        if "_subagent_" in session_id:
            # 提取 subagent_<task_id> 部分
            parts = session_id.split("_subagent_")
            if len(parts) >= 2:
                return f"subagent_{parts[-1]}"
        # 旧格式：subagent_xxxx
        if session_id.startswith("subagent_"):
            return session_id[len("subagent_") :]
        # fork 格式：fork_fork_agent_xxxx
        if session_id.startswith("fork_fork_agent_"):
            return session_id  # 整个 session_id 作为 task_id
        return None

    @staticmethod
    def _detect_tool_failures(chains: List[LLMChain]) -> Dict[str, Dict[str, int]]:
        """检测工具执行失败。

        扫描每次迭代的 request 消息中 role='tool' 的结果，
        通过 tool_errors.detect_tool_failure 匹配错误模式。

        Returns:
            {tool_name: {"failed": count}, ...}
        """
        failures: Dict[str, Dict[str, int]] = {}

        for chain in chains:
            # 从 responses 构建 tool_call_id -> tool_name 映射
            tc_name_map: Dict[str, str] = {}
            for resp in chain.responses:
                for tc in resp.tool_calls:
                    tc_id = tc.get("id", "")
                    name = ChainAnalyzer._extract_tool_name(tc)
                    if tc_id and name:
                        tc_name_map[tc_id] = name

            # 扫描 requests 中的 tool result 消息（去重 by tool_call_id）
            seen_ids: set = set()
            for req in chain.requests:
                for msg in req.body.get("messages", []):
                    if msg.get("role") != "tool":
                        continue
                    tc_id = msg.get("tool_call_id", "")
                    if tc_id in seen_ids:
                        continue
                    seen_ids.add(tc_id)

                    name = tc_name_map.get(tc_id, "unknown")
                    content = msg.get("content", "")
                    if isinstance(content, str) and detect_tool_failure(content)[0]:
                        if name not in failures:
                            failures[name] = {"failed": 0}
                        failures[name]["failed"] += 1

        return failures

    def _compute_statistics(self, sessions: Dict[str, LLMChain]) -> Statistics:
        stats = Statistics()

        parent_chains = [s for s in sessions.values() if not s.is_subagent]
        stats.total_sessions = len(parent_chains)

        total_llm_time = 0.0
        total_tool_time = 0.0
        total_duration = 0.0
        completed_calls_count = 0

        # Token 统计
        total_input_tokens = 0
        total_output_tokens = 0
        total_tokens = 0
        total_cache_tokens = 0
        total_input_cost = 0.0
        total_output_cost = 0.0
        total_cost = 0.0

        # 工具调用统计
        tool_call_counts: Dict[str, int] = {}

        for chain in sessions.values():
            # 工具调用统计（所有 chain 含 subagent）
            for resp in chain.responses:
                if resp.tool_calls:
                    for tc in resp.tool_calls:
                        name = self._extract_tool_name(tc) or "unknown"
                        tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

            if not chain.is_subagent:
                stats.total_requests += len(chain.requests)
                stats.total_responses += len(chain.responses)
                stats.total_iterations += chain.total_iterations

                model = chain.model_name
                stats.sessions_by_model[model] = stats.sessions_by_model.get(model, 0) + 1

                # 时间统计
                total_llm_time += chain.total_llm_duration_seconds
                total_tool_time += chain.total_tool_duration_seconds
                chain_completed = sum(
                    timing.status == CallStatus.COMPLETE for timing in chain.iteration_timings
                )
                chain_invalid = sum(
                    timing.status == CallStatus.INVALID for timing in chain.iteration_timings
                )
                completed_calls_count += chain_completed
                stats.completed_calls += chain_completed
                stats.invalid_calls += chain_invalid
                stats.incomplete_calls += (
                    len(chain.iteration_timings) - chain_completed - chain_invalid
                )

                # Session 总耗时
                if chain.start_time and chain.end_time:
                    total_duration += chain.end_time - chain.start_time

                # Token 统计（从 responses 中累加）
                for resp in chain.responses:
                    total_input_tokens += resp.input_tokens
                    total_output_tokens += resp.output_tokens
                    total_tokens += resp.total_tokens
                    total_cache_tokens += resp.cache_tokens
                    total_input_cost += resp.input_cost
                    total_output_cost += resp.output_cost
                    total_cost += resp.total_cost

        stats.total_duration_seconds = total_duration
        stats.total_llm_time_seconds = total_llm_time
        stats.total_tool_time_seconds = total_tool_time

        # Token 统计
        stats.total_input_tokens = total_input_tokens
        stats.total_output_tokens = total_output_tokens
        stats.total_tokens = total_tokens
        stats.total_cache_tokens = total_cache_tokens
        stats.total_input_cost = total_input_cost
        stats.total_output_cost = total_output_cost
        stats.total_cost = total_cost

        # 工具调用统计
        stats.tool_call_counts = dict(sorted(tool_call_counts.items(), key=lambda x: -x[1]))
        stats.total_tool_calls = sum(tool_call_counts.values())

        # 工具失败统计
        all_chains = list(sessions.values())
        tool_failures = self._detect_tool_failures(all_chains)
        stats.tool_failure_counts = {
            name: data["failed"]
            for name, data in sorted(tool_failures.items(), key=lambda x: -x[1]["failed"])
        }
        stats.failed_tool_calls = sum(stats.tool_failure_counts.values())

        # 计算平均值
        if completed_calls_count > 0:
            stats.avg_llm_time_seconds = total_llm_time / completed_calls_count
            stats.avg_tool_time_seconds = total_tool_time / completed_calls_count

        # Per-session 统计
        for chain in parent_chains:
            s_tokens = sum(r.total_tokens for r in chain.responses)
            s_output_tokens = sum(r.output_tokens for r in chain.responses)
            s_cache_tokens = sum(r.cache_tokens for r in chain.responses)
            s_tool_calls = sum(len(r.tool_calls) for r in chain.responses if r.tool_calls)
            s_reasoning_chars = sum(len(r.reasoning_content or "") for r in chain.responses)
            s_content_chars = sum(len(r.content or "") for r in chain.responses)
            iters = chain.total_iterations
            completed = sum(
                timing.status == CallStatus.COMPLETE for timing in chain.iteration_timings
            )
            total_time = (
                (chain.end_time - chain.start_time) if chain.end_time and chain.start_time else 0
            )
            s_failures = self._detect_tool_failures([chain])
            s_failed = sum(d["failed"] for d in s_failures.values())
            stats.session_stats.append(
                {
                    "session_id": chain.session_id,
                    "model": chain.model_name,
                    "iterations": iters,
                    "total_time": total_time,
                    "llm_time": chain.total_llm_duration_seconds,
                    "tool_time": chain.total_tool_duration_seconds,
                    "completed_calls": completed,
                    "incomplete_calls": iters - completed,
                    "avg_llm_time": (
                        chain.total_llm_duration_seconds / completed if completed > 0 else 0
                    ),
                    "avg_tool_time": (
                        chain.total_tool_duration_seconds / completed if completed > 0 else 0
                    ),
                    "tokens": s_tokens,
                    "output_tokens": s_output_tokens,
                    "cache_tokens": s_cache_tokens,
                    "tokens_per_sec": (
                        s_output_tokens / chain.total_llm_duration_seconds
                        if chain.total_llm_duration_seconds > 0
                        else 0
                    ),
                    "reasoning_chars": s_reasoning_chars,
                    "content_chars": s_content_chars,
                    "tool_calls": s_tool_calls,
                    "failed_tool_calls": s_failed,
                }
            )

        return stats
