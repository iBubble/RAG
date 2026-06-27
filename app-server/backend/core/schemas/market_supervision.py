from pydantic import BaseModel, Field, field_validator
from typing import Literal

class CorporatePenaltyForm(BaseModel):
    company_name: str = Field(..., description="企业全称，需与统一社会信用代码对应")
    credit_code: str = Field(..., description="18位统一社会信用代码")
    penalty_type: Literal["警告", "罚款", "暂扣许可证", "吊销营业执照"] = Field(..., description="法定处罚种类")
    fine_amount_yuan: float = Field(default=0.0, description="罚款金额（元），无罚款则为0")
    legal_basis: str = Field(..., description="适用的具体法律法规条文主旨")

    @field_validator('credit_code')
    def validate_code(cls, v):
        v_strip = v.strip()
        if len(v_strip) != 18:
            raise ValueError("统一社会信用代码必须为 18 位")
        if not v_strip.isalnum():
            raise ValueError("统一社会信用代码必须由数字和英文字母组成")
        return v_strip
