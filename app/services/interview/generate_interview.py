"""
면접 질문 생성 Service (OpenAI API)
"""
import re
import json
import os
from typing import List, Dict
from openai import OpenAI


class GenerateInterviewService:
    """OpenAI API를 사용한 면접 질문 생성"""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @staticmethod
    def split_ko(text: str) -> List[str]:
        """
        간단 한국어 문장 분할기 (추후 kss로 교체 가능)

        Args:
            text: 분할할 텍스트

        Returns:
            문장 리스트
        """
        text = re.sub(r"\s+", " ", text.strip())
        # 종결부호/형식 기반 단순 분할 (MVP)
        # 마침표, 느낌표, 물음표 뒤의 공백으로 분할
        sents = re.split(r'([\.!?])\s+', text)

        # split으로 분리된 문장과 구두점을 재조합
        result = []
        for i in range(0, len(sents)-1, 2):
            sentence = sents[i] + sents[i+1]
            if sentence.strip():
                result.append(sentence.strip())

        # 마지막 문장 처리 (구두점이 없는 경우)
        if len(sents) % 2 == 1 and sents[-1].strip():
            result.append(sents[-1].strip())

        return result

    @staticmethod
    def build_prompt_generate_questions(sentences: List[str], emit_confidence: bool = True) -> str:
        """
        프롬프트 템플릿 빌더

        Args:
            sentences: 자소서 문장 리스트
            emit_confidence: 신뢰도 포함 여부

        Returns:
            프롬프트 문자열
        """
        sentence_block = "\n".join([f"{i+1}) {s}" for i, s in enumerate(sentences)])

        prompt = f"""
<role>
당신은 신입/주니어 개발자 면접관입니다.
</role>

<goal>
아래 자기소개서 문장 리스트를 읽고,
1) 면접가치가 높은 '핵심 문장'을 고른 뒤
2) 각 핵심 문장에 대해 1~3개의 면접 질문을 생성하고
3) 각 질문에 타입(type: job|soft)과 신뢰도(confidence: 0~1)를 부여합니다.
</goal>

<input>
<resume_sentences>
{sentence_block}
</resume_sentences>
</input>

<key_sentence_criteria>
다음 기준 중 하나 이상을 만족하는 문장을 핵심 문장으로 선정하세요:
- 역할/책임: 리더, 담당자, 의사결정자로서의 역할
- 문제-해결: 원인 규명, 해결 전략, 실험, 결과
- 수치/지표: 정량적 성과 (예: 40% 단축, 10만 사용자, p95 latency 50ms 개선)
- 선택/트레이드오프: 여러 대안을 비교하고 선택한 근거
- 협업/갈등: 팀 조율, 합의 도출, 피드백 수용
- 학습/회고: 얻은 교훈, 향후 적용 계획
</key_sentence_criteria>

<question_type_guide>
- job: 직무/기술 중심 질문
  예) 성능 최적화, 테스트 전략, 장애 대응, 데이터 모델링, 아키텍처 설계, 배포 자동화, 보안, 알고리즘, DevOps, FE/BE 개발 등

- soft: 소프트스킬 중심 질문
  예) 협업 방식, 갈등 해결, 리더십 발휘, 커뮤니케이션, 피드백 수용, 책임감, 고객 대응, 윤리적 판단 등

주의: mixed 타입은 사용하지 마세요. job 또는 soft 중 더 강한 쪽을 선택하세요.
</question_type_guide>


<bad_question_examples>
1. "프로젝트에서 어떤 기술 스택을 사용했나요?" (피할 것)
   → 이유: 단순 사실 확인, 누구에게나 물을 수 있는 일반적 질문

2. "팀워크가 중요하다고 생각하나요?" (피할 것)
   → 이유: 추상적, 자소서 내용과 무관, 의견만 묻는 질문

3. "기술적 요구사항을 정리할 때 어떤 방법론을 사용했는지 구체적으로 설명해 주세요." (피할 것)
   → 이유: "구체적으로"라는 애매한 요구, "기술적 요구사항"이 무엇인지 불명확
</bad_question_examples>

<rules>
1. 질문은 한국어, 한 문장, 120자 이내로 작성하세요.
2. 행동기반(STAR: Situation, Task, Action, Result) 질문을 작성하세요.
3. 질문에 "구체적으로", "자세히" 같은 애매한 수식어를 넣지 마세요.
4. 자소서에 등장한 구체적인 용어, 기술명, 숫자, 프로젝트명을 질문에 포함하세요.
5. 중복 억제는 하지 않습니다. (MVP 단계)
6. type은 반드시 "job" 또는 "soft" 중 하나만 사용하세요. "mixed"는 사용 금지입니다.
7. 반드시 JSON 형식만 출력하세요.
</rules>

<output_format>
{{
  "key_sentences": [
    {{
      "index": 2,
      "evidence": "배포 자동화를 통해 출시 시간을 40% 단축했습니다."
    }}
  ],
  "questions": [
    {{
      "text": "자소서에서 '배포 자동화를 통해 출시 시간을 40% 단축했다'고 했는데, 비교했던 대안과 최종 선택의 근거는 무엇이었나요?",
      "type": "job",
      "confidence": 0.85,
      "evidence_index": 2
    }}
  ]
}}
</output_format>
"""
        return prompt

    def ask_llm_for_questions(self, sentences: List[str]) -> dict:
        """
        OpenAI API 호출

        Args:
            sentences: 자소서 문장 리스트

        Returns:
            생성된 질문 데이터
        """
        prompt = self.build_prompt_generate_questions(sentences)
        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",  # 가벼운 모델 권장
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = resp.choices[0].message.content

        # JSON 파싱 (LLM이 JSON만 주도록 규칙을 넣었지만 안전 처리)
        try:
            data = json.loads(content)
        except Exception:
            # JSON 블록만 추출 시도
            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                raise ValueError("LLM 응답에서 JSON을 찾지 못했습니다.")
            data = json.loads(match.group(0))
        return data

    async def generate_from_resume(
        self,
        qas: List[Dict],
        emit_confidence: bool = True,
        use_seed: bool = False,
        top_k_seed: int = 0
    ) -> Dict:
        """
        자소서 기반 면접 질문 생성

        Args:
            qas: [{"q": "질문", "a": "답변"}, ...]
            emit_confidence: 신뢰도 포함 여부
            use_seed: Seed 사용 여부 (MVP: 미사용)
            top_k_seed: Top K Seed (MVP: 0)

        Returns:
            {
                "key_sentences": [...],
                "questions": [...],
                "summary": {...}
            }
        """
        # 1) 문장 분할
        joined = "\n".join([qa["a"].strip() for qa in qas if qa["a"].strip()])
        sentences = self.split_ko(joined)

        # 2) LLM 호출 (seed/중복 억제 없음)
        result = self.ask_llm_for_questions(sentences)

        # 3) 요약/메타 계산
        qs = result.get("questions", [])
        summary = {
            "sentences_total": len(sentences),
            "key_sentences": len(result.get("key_sentences", [])),
            "questions_total": len(qs),
            "job": sum(1 for q in qs if q.get("type") == "job"),
            "soft": sum(1 for q in qs if q.get("type") == "soft"),
        }
        result["summary"] = summary

        return result
