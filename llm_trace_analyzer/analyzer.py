"""链路分析器 - 关联请求/响应并生成统计"""

from typing import Dict, List

from .models import AnalysisResult, LLMChain, LLMRequest, LLMResponse, Statistics


class ChainAnalyzer:
    def __init__(
        self, requests: Dict[str, List[LLMRequest]], responses: Dict[str, List[LLMResponse]]
    ):
        self.requests = requests
        self.responses = responses

    def analyze(self) -> AnalysisResult:
        result = AnalysisResult()

        all_session_ids = set(self.requests.keys()) | set(self.responses.keys())

        for session_id in all_session_ids:
            reqs = self.requests.get(session_id, [])
            resps = self.responses.get(session_id, [])

            if not reqs and not resps:
                continue

            model_name = reqs[0].model_name if reqs else (resps[0].model_name if resps else "")

            chain = LLMChain(
                session_id=session_id,
                model_name=model_name,
                requests=reqs,
                responses=resps,
                start_time=reqs[0].timestamp if reqs else 0,
                end_time=resps[-1].timestamp if resps else 0,
                total_iterations=max(len(reqs), len(resps)),
            )

            result.sessions[session_id] = chain

        result.sorted_sessions = sorted(result.sessions.values(), key=lambda c: c.start_time)

        result.statistics = self._compute_statistics(result.sessions)

        return result

    def _compute_statistics(self, sessions: Dict[str, LLMChain]) -> Statistics:
        stats = Statistics()

        stats.total_sessions = len(sessions)

        for chain in sessions.values():
            stats.total_requests += len(chain.requests)
            stats.total_responses += len(chain.responses)
            stats.total_iterations += chain.total_iterations

            model = chain.model_name
            stats.sessions_by_model[model] = stats.sessions_by_model.get(model, 0) + 1

        return stats
