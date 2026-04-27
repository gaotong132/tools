"""链路分析器 - 关联请求/响应并生成统计"""

from typing import Any, Dict, List, Optional, Tuple

from .models import (
    AnalysisResult,
    LLMChain,
    LLMRequest,
    LLMResponse,
    Statistics,
    SubagentInfo,
)


class ChainAnalyzer:
    def __init__(
        self,
        requests: Dict[str, List[LLMRequest]],
        responses: Dict[str, List[LLMResponse]],
        tool_call_events: List[Dict[str, Any]],
        subagent_start_events: List[Dict[str, Any]],
    ):
        self.requests = requests
        self.responses = responses
        self.tool_call_events = tool_call_events
        self.subagent_start_events = subagent_start_events
        self._parent_to_task_ids: Dict[str, List[Tuple[str, float]]] = {}
        self._task_id_to_parent: Dict[str, str] = {}

    def analyze(self) -> AnalysisResult:
        result = AnalysisResult()

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

        return result

    def _match_spawn_calls_to_task_ids(self) -> None:
        # 处理 spawn_subagent 和 fork_agent
        spawn_calls = [e for e in self.tool_call_events if e.get("tool_name") == "spawn_subagent"]
        fork_calls = [e for e in self.tool_call_events if e.get("tool_name") == "fork_agent"]

        # 新格式：从 session_id 直接提取父子关系
        for session_id in set(self.requests.keys()) | set(self.responses.keys()):
            # spawn_subagent 新格式：<parent>_subagent_<task_id>
            if "_subagent_" in session_id:
                parts = session_id.split("_subagent_")
                if len(parts) >= 2:
                    parent_session = parts[0]
                    if parent_session not in self._parent_to_task_ids:
                        self._parent_to_task_ids[parent_session] = []
                    self._parent_to_task_ids[parent_session].append((session_id, 0))
                    self._task_id_to_parent[session_id] = parent_session

            # fork_agent 新格式：<parent>_fork_agent_<task_id>
            if "_fork_agent_" in session_id:
                parts = session_id.split("_fork_agent_")
                if len(parts) >= 2:
                    parent_session = parts[0]
                    # parent 可能是部分 session_id，需要找到完整匹配
                    # 例如：parent = subagent_af7666eb，完整的是 sess_xxx_subagent_af7666eb
                    full_parent = self._find_full_session_id(parent_session)
                    if full_parent:
                        root_parent = self._find_root_parent(full_parent)
                        if root_parent not in self._parent_to_task_ids:
                            self._parent_to_task_ids[root_parent] = []
                        self._parent_to_task_ids[root_parent].append((session_id, 0))
                        self._task_id_to_parent[session_id] = full_parent  # 记录直接 parent（完整 session_id）
                    else:
                        # parent 不在已知 session 中，直接添加
                        if parent_session not in self._parent_to_task_ids:
                            self._parent_to_task_ids[parent_session] = []
                        self._parent_to_task_ids[parent_session].append((session_id, 0))
                        self._task_id_to_parent[session_id] = parent_session

    def _find_full_session_id(self, partial_id: str) -> Optional[str]:
        """从部分 session_id 找到完整匹配的 session_id"""
        all_sessions = set(self.requests.keys()) | set(self.responses.keys())
        for session_id in all_sessions:
            # 排除 fork session_id（因为它们包含 parent 但不是我们要找的）
            if "_fork_agent_" in session_id:
                continue
            # 检查是否以 partial_id 结尾（例如 sess_xxx_subagent_af7666eb 结尾是 subagent_af7666eb）
            if session_id.endswith(partial_id):
                return session_id
        return None

        # 旧格式 spawn_subagent：通过 subagent_start_events 时间匹配
        if spawn_calls and self.subagent_start_events:
            subagent_starts_sorted = sorted(self.subagent_start_events, key=lambda e: e["timestamp"])

            for spawn_call in spawn_calls:
                parent_session = spawn_call.get("session_id")
                spawn_time = spawn_call.get("timestamp", 0)

                best_match = None
                best_diff = float("inf")

                for start_event in subagent_starts_sorted:
                    start_time = start_event.get("timestamp", 0)
                    time_diff = abs(start_time - spawn_time)

                    if time_diff < best_diff and time_diff < 5.0:
                        best_diff = time_diff
                        best_match = start_event

                if best_match and parent_session:
                    task_id = best_match.get("task_id")
                    if task_id:
                        # 旧格式：session_id = subagent_<task_id>
                        subagent_session = f"subagent_{task_id}"
                        if parent_session not in self._parent_to_task_ids:
                            self._parent_to_task_ids[parent_session] = []
                        self._parent_to_task_ids[parent_session].append((subagent_session, spawn_time))
                        self._task_id_to_parent[subagent_session] = parent_session

        # 匹配 fork_agent：通过 subAgent session_id（fork_fork_agent_xxxx）
        if fork_calls:
            fork_starts_sorted = sorted(fork_calls, key=lambda e: e["timestamp"])

            for session_id in set(self.requests.keys()) | set(self.responses.keys()):
                if not session_id.startswith("fork_fork_agent_"):
                    continue

                task_id = session_id  # 整个 session_id 作为 task_id

                reqs = self.requests.get(session_id, [])
                if not reqs:
                    continue
                first_req_time = min(r.timestamp for r in reqs)

                best_match = None
                best_diff = float("inf")

                for fork_call in fork_starts_sorted:
                    fork_time = fork_call.get("timestamp", 0)
                    time_diff = abs(first_req_time - fork_time)

                    if time_diff < best_diff and time_diff < 5.0:
                        best_diff = time_diff
                        best_match = fork_call

                if best_match:
                    direct_parent = best_match.get("session_id")
                    if direct_parent:
                        root_parent = self._find_root_parent(direct_parent)
                        if root_parent not in self._parent_to_task_ids:
                            self._parent_to_task_ids[root_parent] = []
                        self._parent_to_task_ids[root_parent].append((task_id, best_match["timestamp"]))
                        self._task_id_to_parent[task_id] = direct_parent

    def _find_root_parent(self, session_id: str) -> str:
        """递归向上找到真正的顶层父 session"""
        # 新格式：<parent>_subagent_<task_id> 或 <parent>_fork_agent_<task_id>
        if "_subagent_" in session_id or "_fork_agent_" in session_id:
            # 提取 parent 部分
            if "_subagent_" in session_id:
                parts = session_id.split("_subagent_")
            else:
                parts = session_id.split("_fork_agent_")
            parent = parts[0] if len(parts) >= 2 else session_id
            # 检查 parent 是否也是 subAgent
            if "_subagent_" in parent or "_fork_agent_" in parent:
                return self._find_root_parent(parent)
            return parent
        # 旧格式：subagent_subagent_xxxx（嵌套的 subAgent）
        if session_id.startswith("subagent_subagent_"):
            task_id = session_id[len("subagent_") :]  # subagent_xxxx
            parent = self._task_id_to_parent.get(task_id)
            if parent:
                return self._find_root_parent(parent)
        elif session_id.startswith("fork_fork_agent_"):
            parent = self._task_id_to_parent.get(session_id)
            if parent:
                return self._find_root_parent(parent)
        # 如果不是 subAgent，就是顶层父 session
        return session_id

    def _identify_parent_sessions(self) -> List[str]:
        parent_ids: List[str] = []
        for session_id in set(self.requests.keys()) | set(self.responses.keys()):
            # 排除 spawn_subagent 和 fork_agent 的 subAgent session
            # 旧格式：subagent_xxxx, fork_fork_agent_xxxx
            # 新格式：<parent>_subagent_<task_id>, <parent>_fork_agent_<task_id>
            if not session_id.startswith("subagent_") and not session_id.startswith("fork_fork_agent_") and "_subagent_" not in session_id and "_fork_agent_" not in session_id:
                parent_ids.append(session_id)
        return parent_ids

    def _identify_subagent_sessions(self) -> List[str]:
        subagent_ids: List[str] = []
        for session_id in set(self.requests.keys()) | set(self.responses.keys()):
            # spawn_subagent 旧格式：subagent_xxxx
            # fork_agent 旧格式：fork_fork_agent_xxxx
            # spawn_subagent 新格式：<parent>_subagent_<task_id>
            # fork_agent 新格式：<parent>_fork_agent_<task_id>
            if session_id.startswith("subagent_") or session_id.startswith("fork_fork_agent_") or "_subagent_" in session_id or "_fork_agent_" in session_id:
                subagent_ids.append(session_id)
        return subagent_ids

    def _build_parent_chain(
        self, session_id: str, subagent_sessions: List[str]
    ) -> Optional[LLMChain]:
        reqs = self.requests.get(session_id, [])
        resps = self.responses.get(session_id, [])

        if not reqs and not resps:
            return None

        for req in reqs:
            req.source = "parent"
            req.source_label = "Parent"

        for resp in resps:
            resp.source = "parent"
            resp.source_label = "Parent"

        model_name = reqs[0].model_name if reqs else (resps[0].model_name if resps else "")

        related_subagents = self._find_related_subagents(session_id)

        subagent_infos: List[SubagentInfo] = []
        for task_id, spawn_time in related_subagents:
            # 确定 subAgent session_id
            # 新格式：task_id 就是完整的 session_id（包含 _subagent_ 或 _fork_agent_）
            # 旧格式 fork_agent: task_id = fork_fork_agent_xxxx
            # 旧格式 spawn_subagent: task_id = xxxx, session_id = subagent_{task_id}
            if "_subagent_" in task_id or "_fork_agent_" in task_id:
                subagent_session = task_id
            elif task_id.startswith("fork_fork_agent_"):
                subagent_session = task_id
            else:
                subagent_session = f"subagent_{task_id}"

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
            # 确定 subAgent session_id
            # 新格式：task_id 就是完整的 session_id（包含 _subagent_ 或 _fork_agent_）
            if "_subagent_" in task_id or "_fork_agent_" in task_id:
                subagent_session = task_id
            elif task_id.startswith("fork_fork_agent_"):
                subagent_session = task_id
            else:
                subagent_session = f"subagent_{task_id}"

            # 计算嵌套深度和路径用于显示
            depth, chain_path, direct_parent = self._compute_subagent_depth(task_id)

            if subagent_session in self.requests:
                for req in self.requests[subagent_session]:
                    req.source = "subagent"
                    req.source_label = self._format_chain_label(chain_path, depth)
                    all_requests.append(req)
            if subagent_session in self.responses:
                for resp in self.responses[subagent_session]:
                    resp.source = "subagent"
                    resp.source_label = self._format_chain_label(chain_path, depth)
                    all_responses.append(resp)

        all_requests.sort(key=lambda r: r.timestamp)
        all_responses.sort(key=lambda r: r.timestamp)

        start_time = all_requests[0].timestamp if all_requests else 0
        end_time = all_responses[-1].timestamp if all_responses else 0

        return LLMChain(
            session_id=session_id,
            model_name=model_name,
            requests=all_requests,
            responses=all_responses,
            start_time=start_time,
            end_time=end_time,
            total_iterations=len(all_requests),
            subagents=subagent_infos,
            is_subagent=False,
        )

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
        elif "_subagent_" in task_id:
            chain_path.append(f"Sub[{current_short_name}]")
        elif task_id.startswith("fork_fork_agent_"):
            chain_path.append(f"Fork[{current_short_name}]")
        else:
            chain_path.append(f"Sub[{current_short_name}]")

        current_task_id = task_id
        while True:
            # 从映射表获取 parent
            parent_session = self._task_id_to_parent.get(current_task_id)

            if not parent_session:
                chain_path.insert(0, "Parent")
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
                chain_path.insert(0, "Parent")
                break

        return depth, chain_path, direct_parent

    def _format_chain_label(self, chain_path: List[str], depth: int) -> str:
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

        return LLMChain(
            session_id=session_id,
            model_name=model_name,
            requests=reqs,
            responses=resps,
            start_time=reqs[0].timestamp if reqs else 0,
            end_time=resps[-1].timestamp if resps else 0,
            total_iterations=len(reqs),
            is_subagent=True,
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

    def _compute_statistics(self, sessions: Dict[str, LLMChain]) -> Statistics:
        stats = Statistics()

        stats.total_sessions = len([s for s in sessions.values() if not s.is_subagent])

        for chain in sessions.values():
            if not chain.is_subagent:
                stats.total_requests += len(chain.requests)
                stats.total_responses += len(chain.responses)
                stats.total_iterations += chain.total_iterations

                model = chain.model_name
                stats.sessions_by_model[model] = stats.sessions_by_model.get(model, 0) + 1

        return stats
