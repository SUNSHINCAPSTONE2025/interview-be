"""
면접 관련 비즈니스 로직
- 면접 등록
- 자소서 조회
- 데이터 변환
"""
from typing import Dict, List, Tuple
from fastapi import HTTPException
from app.services import supabase_client as db


class InterviewService:
    """면접 관련 비즈니스 로직"""

    @staticmethod
    def create_interview_with_resumes(
        user_id: int,
        company: str,
        role: str,
        role_category: int,
        interview_date: str,
        jd_text: str,
        resumes: List[Dict]
    ) -> Tuple[Dict, List[Dict]]:
        """
        면접 정보 + 자소서 저장

        Returns:
            (created_content, created_resumes)
        """
        # 1. content 저장
        content_data = {
            "user_id": user_id,
            "company": company,
            "role": role,
            "role_category": role_category,
            "interview_date": interview_date,
            "jd_text": jd_text
        }

        try:
            created_content = db.create_content(content_data)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"message": "content_creation_failed", "detail": str(e)}
            )

        if not created_content:
            raise HTTPException(
                status_code=500,
                detail={"message": "content_creation_failed", "detail": "DB returned no data"}
            )

        # 2. resume 저장
        content_id = created_content["id"]
        version = 1

        resume_data_list = [
            {
                "user_id": user_id,
                "content_id": content_id,
                "version": version,
                "question": item["question"],
                "answer": item["answer"]
            }
            for item in resumes
        ]

        try:
            created_resumes = db.create_resumes_bulk(resume_data_list)
        except Exception as e:
            # Rollback 고려
            # db.delete_content(content_id)
            raise HTTPException(
                status_code=500,
                detail={"message": "resume_creation_failed", "detail": str(e)}
            )

        if not created_resumes:
            raise HTTPException(
                status_code=500,
                detail={"message": "resume_creation_failed", "detail": "DB returned no data"}
            )

        return created_content, created_resumes

    @staticmethod
    def get_interview_by_id(user_id: int, content_id: int) -> Dict:
        """
        면접 정보 조회 (소유권 검증 포함)

        Args:
            user_id: 사용자 ID
            content_id: 면접 ID

        Returns:
            면접 정보

        Raises:
            HTTPException: 404 (없음), 403 (권한 없음)
        """
        content = db.get_content_by_id(content_id)

        if not content:
            raise HTTPException(
                status_code=404,
                detail={"message": "content_not_found"}
            )

        if content["user_id"] != user_id:
            raise HTTPException(
                status_code=403,
                detail={"message": "forbidden", "detail": "Not authorized"}
            )

        return content

    @staticmethod
    def get_resumes_by_content(user_id: int, content_id: int) -> List[Dict]:
        """
        자소서 조회 (소유권 검증 포함)

        Args:
            user_id: 사용자 ID
            content_id: 면접 ID

        Returns:
            자소서 목록

        Raises:
            HTTPException: 404 (없음), 403 (권한 없음)
        """
        # 소유권 검증
        InterviewService.get_interview_by_id(user_id, content_id)

        # 자소서 조회
        resumes = db.get_resumes_by_content(content_id)

        if not resumes:
            raise HTTPException(
                status_code=404,
                detail={"message": "resumes_not_found", "detail": "No resumes for this content"}
            )

        return resumes

    @staticmethod
    def convert_resumes_to_qas(resumes: List[Dict]) -> List[Dict]:
        """
        자소서 데이터를 OpenAI API 형태로 변환

        Args:
            resumes: [{"question": "...", "answer": "..."}, ...]

        Returns:
            [{"q": "...", "a": "..."}, ...]
        """
        return [{"q": r["question"], "a": r["answer"]} for r in resumes]