import json
from typing import Dict

from openai import OpenAI


SYSTEM_PROMPT = """
너는 한국어 면접 코치이다. 사용자의 답변을 분석하되 최종 출력은 아래 JSON 형식만 사용하라:

{
  "overall_summary": ""
}

규칙:
- JSON 외 다른 텍스트 절대 금지
- 필드명/구조 변경 금지 (overall_summary만)
- 한국어 작성, '~합니다'체
- 정확히 4문장
- 관점: 코치가 지원자에게 피드백하는 형태 (2인칭)

overall_summary 작성 기준:
1문장: 답변의 전체 인상 + 강점 1~2개
2문장: 말버릇/반복 표현의 문제 또는 강점
3문장: 문법/단어 선택 문제 또는 강점, 필요 시 대체 표현 제안
4문장: 개선이 필요한 경우 구체적 전략 3가지 이유와 함께 1문장에 자연스럽게 포함 / 개선점 거의 없으면 유지하면 좋은 좋은 말하기 습관 1가지 + 앞으로의 연습 방향 제안

금지:
- 점수화, 번호 나열(첫째/둘째), 불필요한 비유, 마크다운, 줄바꿈
"""

MODEL_NAME = "gpt-4o-mini"


class AnswerEvaluationService:

    @staticmethod
    def evaluate_answer(answer_text: str) -> Dict:
        client = OpenAI()

        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": answer_text},
                ],
            )

            content = completion.choices[0].message.content
            data = json.loads(content)

            if "overall_summary" not in data:
                data["overall_summary"] = "모델이 overall_summary 필드를 반환하지 않았습니다."

            return data

        except Exception as e:
            return {
                "overall_summary": f"LLM 평가 중 오류가 발생했습니다: {str(e)}",
            }