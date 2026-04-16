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
        spawn_calls = [e for e in self.tool_call_events if e.get("tool_name") == "spawn_subagent"]

        if not spawn_calls or not self.subagent_start_events:
            return

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

    def _identify_parent_sessions(self) -> List[str]:
        parent_ids: List[str] = []
        for session_id in set(self.requests.keys()) | set(self.responses.keys()):
            if not session_id.startswith("subagent_"):
                parent_ids.append(session_id)
        return parent_ids

    def _identify_subagent_sessions(self) -> List[str]:
        subagent_ids: List[str] = []
        for session_id in set(self.requests.keys()) | set(self.responses.keys()):
            if session_id.startswith("subagent_"):
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
        parts = task_id.split("_")
        if len(parts) >= 2:
            return parts[-1][:12]
        return task_id[:12]

    def _extract_task_id_from_session(self, session_id: str) -> Optional[str]:
        if session_id.startswith("subagent_"):
            return session_id[len("subagent_") :]
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
