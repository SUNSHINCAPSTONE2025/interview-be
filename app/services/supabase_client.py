import os
from supabase import create_client, Client
from typing import Dict,List,Optional # return type info

# supabase client 초기화
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_key or not supabase_url:
     raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(supabase_url,supabase_key)


# --content table--

# 면접정보 저장
def create_content(data: Dict) -> Dict:
    response = supabase.table("content").insert(data).execute()
    return response.data[0] if response.data else None

# 면접정보 조회 (ID로)
def get_content_by_id(content_id: int) -> Optional[Dict]:
    response = supabase.table("content").select("*").eq("id", content_id).execute()
    return response.data[0] if response.data else None

# 면접정보 수정
def update_content(content_id: int, data: Dict) -> Dict:
    response = supabase.table("content").update(data).eq("id", content_id).execute()
    return response.data[0] if response.data else None

# 면접정보 삭제
def delete_content(content_id: int) -> bool:
    response = supabase.table("content").delete().eq("id", content_id).execute()
    return len(response.data) > 0

# 유저 별 면접 정보 조회
def get_contents_by_user(user_id: int) -> List[Dict]:
    response = supabase.table("content").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return response.data if response.data else []


# --resume table--

# 자소서 저장
def create_resume(data:Dict) -> Dict:
     response = supabase.table("resume").insert(data).execute()
     return response.data[0] if response.data else None

# 여러 자소서 한번에 저장
def create_resumes_bulk(data_list: List[Dict]) -> List[Dict]:
    response = supabase.table("resume").insert(data_list).execute()
    return response.data if response.data else []

# content_id로 자소서 조회 (OpenAI API 요청용)
def get_resumes_by_content(content_id: int) -> List[Dict]:
    response = supabase.table("resume").select("*").eq("content_id", content_id).execute()
    return response.data if response.data else []

# user_id로 자소서 조회 (특정 버전)
def get_resumes_by_user_and_version(user_id: int, version: Optional[int] = None) -> List[Dict]:
    query = supabase.table("resume").select("*").eq("user_id", user_id)
    if version is not None:
        query = query.eq("version", version)
    response = query.execute()
    return response.data if response.data else []