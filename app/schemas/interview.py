from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import Optional, List

# -- Request --

# 자소서 항목 (+최대 자소서 항목 추가)
class ResumeItem(BaseModel):
    question : str = Field(...,min_length=1,max_length=50,description="자소서 질문")
    answer : str = Field(...,min_length=1,max_length=5000,description="자소서 답변")

# 면접 등록 - 요청
class InterviewRegisterRequest(BaseModel):
    company: str = Field(..., min_length=1, max_length=20, description="회사명")
    role: str = Field(..., min_length=1, max_length=20, description="직무명")
    role_category: Optional[int] = Field(None, description="직무 분류 코드")
    interview_date: date = Field(..., description="면접 일자")
    jd_text: Optional[str] = Field(None, description="JD 원문")
    resumes : List[ResumeItem] = Field(...,min_items=1,max_items=5,description="자기소개서 목록") #최대 5개

    @field_validator('interview_date') #모델의 특정 필드를 검증
    @classmethod
    def validate(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("면접 일자는 오늘 이후 날짜여야합니다.")
    
        return v
    

# -- Response --

# 면접 응답
class ContentResponse(BaseModel):
    id: int
    user_id: int
    company: str
    role: str
    role_category: Optional[int]
    interview_date: date
    jd_text: Optional[str]
    created_at: str

class ResumeResponse(BaseModel):
    id: int
    user_id: int
    content_id: int
    version: int
    question: str
    answer: str

# 면접 응답 - 응답
class InterviewRegisterResponse(BaseModel):
    message : str
    content : ContentResponse
    resumes: List[ResumeResponse]
