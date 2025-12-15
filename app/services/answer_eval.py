import json
from typing import Dict

from openai import OpenAI

MODEL_NAME = "gpt-4o-mini"


SHORT_PROMPT = """
너는 한국어 면접 코치이다. 사용자의 답변을 분석하되 최종 출력은 아래 JSON 형식만 사용하라:

{
  "overall_summary": ""
}

규칙:
- JSON 외 다른 텍스트 절대 금지.
- 필드명과 구조를 변경하지 말고 overall_summary만 사용한다.
- overall_summary는 반드시 '정확히 2문장'으로 작성한다.
- 두 문장 모두 한국어로 작성하고 '~합니다'체로 끝낸다.
- 관점: 코치가 지원자에게 직접 피드백하는 형태(2인칭)로 작성한다.
- 점수화, 번호 나열(예: 첫째, 둘째), 비유, 마크다운, 줄바꿈, 목록 사용 금지.

overall_summary 작성 기준:
1문장: 답변의 전체 인상과, 답변이 지나치게 짧아 드러나지 않는 부분을 간단히 설명한다.
2문장: 어떤 내용(경험, 상황, 행동, 결과 등)을 추가하면 답변이 더 좋아질지 한 문장 안에서 구체적으로 제안한다.
"""


STANDARD_PROMPT = """
너는 한국어 면접 코치이다. 사용자의 답변을 분석하되 최종 출력은 아래 JSON 형식만 사용하라:

{
  "overall_summary": ""
}

규칙:
- JSON 외 다른 텍스트 절대 금지.
- 필드명과 구조를 변경하지 말고 overall_summary만 사용한다.
- overall_summary는 반드시 '정확히 4문장'으로 작성한다.
- 모든 문장을 한국어로 작성하고 '~합니다'체로 끝낸다.
- 관점: 코치가 지원자에게 직접 피드백하는 형태(2인칭)으로 작성한다.
- 점수화, 번호 나열(예: 첫째, 둘째), 비유, 마크다운, 줄바꿈, 목록 사용 금지.

overall_summary 작성 기준:
1문장: 답변의 전체 인상과 주요 강점 1~2개를 간단히 정리한다.
2문장: 말버릇이나 반복 표현에서 드러나는 문제점 또는 강점을 짚어 준다.
3문장: 문법, 문장 구조, 단어 선택의 문제 또는 개선 가능한 표현을 설명하고, 필요하면 더 나은 대체 표현을 한두 개 제안한다.
4문장: 답변이 전반적으로 개선이 필요하다면 핵심 개선 전략 2~3가지를 한 문장 안에 자연스럽게 제시하고, 개선점이 거의 없다면 유지하면 좋은 말하기 습관 1가지와 앞으로의 연습 방향을 제안한다.
"""


def classify_length(answer_text: str) -> str:
    
    num_chars = len(answer_text.replace(" ", ""))

    if num_chars < 80:
        return "very_short"   
    elif num_chars < 300:
        return "normal"       
    else:
        return "long"         


class AnswerEvaluationService:

    @staticmethod
    def evaluate_answer(answer_text: str) -> Dict:
        client = OpenAI()

        # 길이에 따라 사용할 프롬프트 선택
        length_label = classify_length(answer_text or "")
        if length_label == "very_short":
            system_prompt = SHORT_PROMPT
        else:
            system_prompt = STANDARD_PROMPT

        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                response_format={"type": "json_object"},
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": answer_text},
                ],
            )

            content = completion.choices[0].message.content
            data = json.loads(content)

            if "overall_summary" not in data:
                data["overall_summary"] = "모델이 overall_summary 필드를 반환하지 않았습니다."

            return data

        except Exception:
            return {
                "overall_summary": "현재 답변 평가 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            }