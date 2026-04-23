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

        # 匹配 spawn_subagent：通过 subagent_start_events
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
                        if parent_session not in self._parent_to_task_ids:
                            self._parent_to_task_ids[parent_session] = []
                        self._parent_to_task_ids[parent_session].append((task_id, spawn_time))
                        self._task_id_to_parent[task_id] = parent_session

        # 匹配 fork_agent：通过 subAgent session_id（fork_fork_agent_xxxx）
        # 在 subAgent 的第一个 stream_request 的时间戳附近找 fork_agent ToolCall
        if fork_calls:
            fork_starts_sorted = sorted(fork_calls, key=lambda e: e["timestamp"])

            for session_id in set(self.requests.keys()) | set(self.responses.keys()):
                if not session_id.startswith("fork_fork_agent_"):
                    continue

                # 提取 task_id（fork_fork_agent_ 后缀）
                task_id = session_id  # 整个 session_id 作为 task_id

                # 找到该 subAgent 的第一个 request 的时间戳
                reqs = self.requests.get(session_id, [])
                if not reqs:
                    continue
                first_req_time = min(r.timestamp for r in reqs)

                # 在 fork_agent ToolCall 中找最接近的
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
                        # 递归向上找到真正的顶层父 session
                        root_parent = self._find_root_parent(direct_parent)
                        if root_parent not in self._parent_to_task_ids:
                            self._parent_to_task_ids[root_parent] = []
                        self._parent_to_task_ids[root_parent].append((task_id, best_match["timestamp"]))
                        self._task_id_to_parent[task_id] = direct_parent  # 记录直接调用者

    def _find_root_parent(self, session_id: str) -> str:
        """递归向上找到真正的顶层父 session"""
        # 如果是 subAgent，向上查找
        if session_id.startswith("subagent_subagent_"):
            # 从 session_id 提取 task_id：subagent_subagent_xxxx -> subagent_xxxx
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
            if not session_id.startswith("subagent_") and not session_id.startswith("fork_fork_agent_"):
                parent_ids.append(session_id)
        return parent_ids

    def _identify_subagent_sessions(self) -> List[str]:
        subagent_ids: List[str] = []
        for session_id in set(self.requests.keys()) | set(self.responses.keys()):
            # spawn_subagent 格式：subagent_xxxx
            # fork_agent 格式：fork_fork_agent_xxxx
            if session_id.startswith("subagent_") or session_id.startswith("fork_fork_agent_"):
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
            # spawn_subagent: task_id = xxxx, session_id = subagent_{task_id}
            # fork_agent: task_id = fork_fork_agent_xxxx, session_id = task_id
            if task_id.startswith("fork_fork_agent_"):
                subagent_session = task_id
            else:
                subagent_session = f"subagent_{task_id}"

            if subagent_session in subagent_sessions:
                subagent_reqs = self.requests.get(subagent_session, [])
                subagent_resps = self.responses.get(subagent_session, [])
                sub_start = subagent_reqs[0].timestamp if subagent_reqs else spawn_time
                sub_end = subagent_resps[-1].timestamp if subagent_resps else 0.0
                subagent_infos.append(
                    SubagentInfo(
                        task_id=task_id,
                        session_id=subagent_session,
                        start_time=sub_start,
                        end_time=sub_end,
                    )
                )

        all_requests: List[LLMRequest] = list(reqs)
        all_responses: List[LLMResponse] = list(resps)

        for task_id, _ in related_subagents:
            # 确定 subAgent session_id
            if task_id.startswith("fork_fork_agent_"):
                subagent_session = task_id
            else:
                subagent_session = f"subagent_{task_id}"

            if subagent_session in self.requests:
                for req in self.requests[subagent_session]:
                    req.source = "subagent"
                    req.source_label = f"Subagent [{self._short_task_id(task_id)}]"
                    all_requests.append(req)
            if subagent_session in self.responses:
                for resp in self.responses[subagent_session]:
                    resp.source = "subagent"
                    resp.source_label = f"Subagent [{self._short_task_id(task_id)}]"
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
        # fork_fork_agent_xxxx 格式
        if task_id.startswith("fork_fork_agent_"):
            suffix = task_id[len("fork_fork_agent_") :]
            return f"fork_{suffix[:8]}"
        # subagent_xxxx 格式
        parts = task_id.split("_")
        if len(parts) >= 2:
            return parts[-1][:12]
        return task_id[:12]

    def _extract_task_id_from_session(self, session_id: str) -> Optional[str]:
        if session_id.startswith("subagent_"):
            return session_id[len("subagent_") :]
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
