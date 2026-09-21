"""business_code -> 专属分类提示词 -> 具体类型 -> 专属取数提示词。"""

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

import httpx

from app import config


@dataclass(frozen=True)
class DocumentTypeConfig:
    name: str
    description: str
    extraction_prompt: str
    response_template: Mapping[str, Any]


@dataclass(frozen=True)
class BusinessConfig:
    classification_prompt: str
    document_types: Mapping[str, DocumentTypeConfig]


COMMON_EXTRACTION_RULES = """
只能依据原文取数，不允许猜测或补充。字符串缺失返回空字符串，数组缺失返回空数组。
必须只返回合法 JSON；字段名称、层级和数据类型必须与固定返回结构完全一致，不得增加字段。
固定返回结构：
{response_template}
"""


# 每个 business_code 有独立分类提示词；每个具体类型有独立取数提示词和固定返回结构。
#
# 维护示例（复制到对应的 business_code 中填写）：
# BusinessConfig(
#     classification_prompt="""你的业务分类提示词：\n{type_options}\n"
#                           "只返回 JSON：{{\"document_type\":\"类型编码\"}}。""",
#     document_types={
#         "your_document_type": DocumentTypeConfig(
#             name="类型名称",
#             description="供分类模型识别该类型的说明",
#             extraction_prompt="""该类型专属取数提示词。\n{common_rules}""",
#             response_template={"field_name": "", "list_field": []},
#         ),
#     },
# )
BUSINESS_CONFIGS: Mapping[str, BusinessConfig] = {
    "0": BusinessConfig(
        classification_prompt="""## 文档类型分类说明
优先根据文档标题和封面信息判断，并结合核心内容和典型字段交叉验证；若同时具备多类特征，以核心内容和主要目的为准。每份文档只返回一个类型。

候选类型：
{type_options}

分类要点：
1. 财务尽调报告：标题含“财务尽职调查报告”“财务尽调”，以多期财务数据、财务报表和指标分析为核心。
2. 估值报告：标题或内容含“估值报告”“资产评估”“投资价值分析”，核心为估值模型、参数和结论。
3. 法律尽调报告：通常由律师事务所出具，围绕公司设立、股权、合同、诉讼及合规展开。
4. 会议纪要：标题含“会议纪要”“总经理办公会”“投决会会议纪要”，包含会议信息、议案及审议意见。
5. 投资协议：标题含“投资协议”“增资协议”“股权转让协议”，具有协议主体及合同条款编号。
6. 物资废料申报文件：标题含“废料处置申报”“废旧物资申报单”“报废物料清单”等，以物料明细为核心。
7. 其他：无法明确归入以上类型。

只返回合法 JSON：{{"document_type":"类型编码"}}，不得输出解释。""",
        document_types={
            "financial_due_diligence": DocumentTypeConfig(
                name="财务尽调",
                description="财务尽调报告，包含利润表、资产负债表、现金流量表及多期财务指标",
                extraction_prompt="""你是财务尽调报告专项抽取引擎，同时抽取利润表、资产负债表和现金流量表。
优先提取合并报表；无合并报表时提取现有财务报表。金额统一换算为元并保留两位小数，比率保留原文。
基础字段 company_name、report_date、work_end_date 优先从封面、首页提取；同一指标多处出现时以核心财务页为准。
利润表标准指标包括：营业收入、营业成本、税金及附加、销售费用、管理费用、研发费用、财务费用、其他收益、公允价值变动收益、投资收益、营业利润、营业外收入、营业外支出、利润总额、所得税费用、净利润、成本收入比。
资产负债表标准指标包括：货币资金、应收票据、应收账款、预付款项、其他应收款、存货、固定资产、无形资产、在建工程、短期借款、应付票据、应付账款、预收款项、应付职工薪酬、应交税费、其他应付款、长期借款、总资产、总负债、所有者权益、资产负债率。
现金流量表标准指标包括：经营活动现金净流入、销售商品收到的现金、购买商品支付的现金、支付职工现金、支付各项税费、投资活动现金流量净额、购建固定资产支付现金、取得投资收回现金、筹资活动现金流量净额、取得借款收到现金、偿还借款支付现金、分配股利支付现金。
原文科目能匹配标准指标时统一名称；不能匹配时保留原始名称。所有可见科目应提尽提，不得遗漏。正文双引号统一替换为中文单引号。
financial_indicators 中每个期间使用 {{"date":"", "data":[{{"indicator_name":"", "indicator_value":""}}]}} 结构。
{common_rules}""",
                response_template={
                    "company_name": "", "report_date": "", "work_end_date": "",
                    "income_statement": {"financial_indicators": []},
                    "balance_sheet": {"financial_indicators": []},
                    "cash_flow_statement": {"financial_indicators": []},
                },
            ),
            "valuation_report": DocumentTypeConfig(
                name="估值报告",
                description="估值、资产评估或投资价值分析报告",
                extraction_prompt="""你是估值报告专项数据抽取引擎，仅解析估值报告正文并提取估值测算指标。
区分评估基准日和报告出具日期。标准指标包括 WACC、年回报率、预期投资回报率、内部收益率、IRR；能匹配时使用标准名称，其他收益、折现、回报类指标保留原名并应提尽提。
百分比保留原文，金额统一换算为元的纯数字。project_name 不要包含“估值报告”四个字。正文双引号统一替换为中文单引号。
financial_indicators 元素结构为 {{"indicator_name":"", "indicator_value":""}}。
{common_rules}""",
                response_template={
                    "project_name": "", "valuation_base_date": "", "report_issue_date": "",
                    "valuation_unit": "", "financial_indicators": [],
                },
            ),
            "legal_due_diligence": DocumentTypeConfig(
                name="法律尽调报告",
                description="律师事务所出具的法律尽职调查报告",
                extraction_prompt="""你是法律尽调报告专项数据抽取引擎，仅解析法律尽调报告。
被投企业名称优先取封面目标企业全称；项目名称优先取引言页完整投资入股项目名称；报告时间优先取首页出具日期。正文双引号统一替换为中文单引号。
{common_rules}""",
                response_template={
                    "invested_company_name": "", "project_full_name": "", "legal_report_date": "",
                },
            ),
            "meeting_minutes": DocumentTypeConfig(
                name="会议纪要",
                description="会议基本信息、议案、审议意见和参会人员组成的会议纪要",
                extraction_prompt="""你是会议纪要专项数据抽取引擎，仅提取会议纪要信息。
会议名称、时间优先从开头提取；所有议案逐条完整提取，意见仅提取审议意见相关内容；参会人员拆分姓名、角色和职位。正文双引号统一替换为中文单引号。
proposals 元素结构为 {{"proposal_name":"", "opinion_content":""}}；participants 元素结构为 {{"name":"", "role":"", "position":""}}。
{common_rules}""",
                response_template={
                    "meeting_name": "", "meeting_time": "", "proposals": [], "participants": [],
                },
            ),
            "investment_agreement": DocumentTypeConfig(
                name="投资协议",
                description="投资、增资、股权转让或股权回购赎回类协议",
                extraction_prompt="""你是投资协议专项抽取引擎，一次完成基础指标、主体账户及核心交易关系抽取。
基础指标固定为：协议名称、协议编码、签订日期、对赌条款、预计上市时间安排、首次公开发行时间、回购条款、回购约定时间、回购触发情形、违约条款信息。长条款完整摘录核心原文。
account_list 提取银行账号、户名、开户行、收付款类型、付款期限。收付款类型限：投资款收入/支出、股权转让款收入/支出、股权赎回款收入/支出、股权回购款收入/支出、保证金收入/支出、违约金/罚息赔付收入/支出。
company_list 提取企业全称、角色、信用代码和地址。企业角色限：投资方、被投方（标的企业）、转让方（出让方）、受让方（收购方）、回购方、赎回方、担保方、居间方/中介方、见证方。
person_list 提取姓名、电话、身份证、个人角色及关联主体；法定代表人关联所属企业，授权代理人关联代理企业，担保人关联被担保主体。当前轮主体角色增加“当前轮”前缀。
trade_relation_list 仅记录资金、股权流转。from 为流出方，to 为流入方，金额统一为元；remark 优先使用增资款、融资款、股权转让款、股权回购款、股权赎回款、保证金/押金、违约金/罚息，并可在【】内保留资金细分用途。
正文双引号统一替换为中文单引号。
base_indicators 元素结构：{{"indicator_name":"", "indicator_value":""}}；account_list 元素结构：{{"account_no":"", "account_name":"", "bank_name":"", "pay_type":"", "pay_deadline":""}}；company_list 元素结构：{{"company_name":"", "company_role":"", "credit_code":"", "address":""}}；person_list 元素结构：{{"name":"", "phone":"", "id_card":"", "person_role":"", "related_subject":""}}；trade_relation_list 元素结构：{{"from":"", "to":"", "amount":"", "currency":"", "ratio":"", "remark":""}}。
{common_rules}""",
                response_template={
                    "base_indicators": [], "account_list": [], "company_list": [],
                    "person_list": [], "trade_relation_list": [],
                },
            ),
            "waste_materials": DocumentTypeConfig(
                name="废料物资",
                description="废料处置申报、废旧物资申报或报废物料清单",
                extraction_prompt="""你是物资废料申报文件专项数据抽取引擎，仅提取废料申报信息。
file_name 取文档完整标题；declare_company 从申报抬头、落款或申报主体栏提取；所有物料逐条完整抓取。
materials 是二维数组，每条固定顺序为：[物料完整名称, 物料数量, 计量单位, 规格型号, 预估重量(吨)]。正文双引号统一替换为中文单引号。
{common_rules}""",
                response_template={"file_name": "", "declare_company": "", "materials": []},
            ),
            "other": DocumentTypeConfig(
                name="其他",
                description="无法归入以上类型的文档",
                extraction_prompt="""该文档属于其他类型，不做业务字段提取，只返回空 JSON 对象。{common_rules}""",
                response_template={},
            ),
        },
    ),
    "1": BusinessConfig(
        classification_prompt="""### 分类识别判断规则
匹配优先级：文档名称/标题/封面名称 > 正文核心内容、典型字段；每份文档只返回唯一分类。冲突时以主标题、核心用途和核心内容为准。

候选类型：
{type_options}

1. 项目评审意见书：标题含“项目评审意见书”，或含项目编码、还款能力、担保能力、合规分析、风险等级、评审结论等内容。
2. 固有业务尽调报告：标题含“固有”“固有业务”“尽调报告”“尽职调查报告”，并包含交易对手、业务、法律、风险、投资核查分析。
3. 财务报告：以企业合并资产负债表、利润表、现金流量表为核心，包含标准化多期财务数据；仅附带少量财务数据的不归此类。
4. 其他：无法匹配以上三类。

只返回合法 JSON：{{"document_type":"类型编码"}}，不得输出解释。""",
        document_types={
            "project_review_opinion": DocumentTypeConfig(
                name="项目评审意见书",
                description="包含项目编码、风险等级、分析内容及最终评审结论",
                extraction_prompt="""你是百瑞信托项目评审意见书专项抽取引擎，仅解析项目评审意见书。
字段优先取首页 P1，分析内容依次取 P1-P4 正文；同一指标多处出现时以首页核心评审页为准。百分比、风险等级和描述保留原文。
borrower_analysis 提取还款能力、股东背景、经营情况、财务情况、整体情况；guarantor_analysis 提取担保能力及相同维度；risk_analysis 提取合规性、受托责任、受托责任风险、交易模式合规法律分析和收入资本比。正文双引号统一替换为中文单引号。
{common_rules}""",
                response_template={
                    "project_name": "", "review_code": "", "submit_department": "",
                    "review_basis": "", "risk_level": "", "review_conclusion": "",
                    "borrower_analysis": [], "guarantor_analysis": [], "risk_analysis": [],
                },
            ),
            "proprietary_due_diligence": DocumentTypeConfig(
                name="固有业务尽调报告",
                description="针对固有业务的交易对手、业务、法律、风险及投资核查报告",
                extraction_prompt="""你是百瑞信托固有业务尽调报告专项数据抽取引擎。
项目名称、项目类型、提交部门、提交日期优先取封面首页；IRR、ROI、资金成本覆盖、流动性匹配、投资期限和财务报表情况取自测算及财务分析章节。同一指标多处出现时以首页核心测算页为准。原文完整摘抄，不精简、改写或概括。正文双引号统一替换为中文单引号。
{common_rules}""",
                response_template={
                    "project_trust_name": "", "submit_department": "", "submit_date": "",
                    "irr": "", "roi": "", "cover_capital_cost": "", "liquidity_match": "",
                    "invest_term": "", "has_financial_statement": "",
                },
            ),
            "financial_report": DocumentTypeConfig(
                name="财务报告",
                description="以资产负债表、利润表和现金流量表为核心的专项财务文件",
                extraction_prompt="""你是财务报告三张表专项抽取引擎，同时提取利润表、资产负债表和现金流量表。
优先提取合并报表，无合并报表时读取现有报表；金额统一换算为元并保留两位小数，比率保留原文。company_name、project_name 优先从文件名、封面、首页提取，同一指标以核心财务页为准。
利润表标准指标：营业收入、营业成本、税金及附加、销售费用、管理费用、研发费用、财务费用、其他收益、公允价值变动收益、投资收益、营业利润、营业外收入、营业外支出、利润总额、所得税费用、净利润、成本收入比。
资产负债表标准指标：货币资金、应收票据、应收账款、预付款项、其他应收款、存货、固定资产、无形资产、在建工程、短期借款、应付票据、应付账款、预收款项、应付职工薪酬、应交税费、其他应付款、长期借款、总资产、总负债、所有者权益、资产负债率。
现金流量表标准指标：经营活动现金净流入、销售商品收到的现金、购买商品支付的现金、支付职工现金、支付各项税费、投资活动现金流量净额、购建固定资产支付现金、取得投资收回现金、筹资活动现金流量净额、取得借款收到现金、偿还借款支付现金、分配股利支付现金。
不能匹配标准枚举的科目保留原始名称，所有可见科目应提尽提。正文双引号统一替换为中文单引号。
{common_rules}""",
                response_template={
                    "company_name": "", "project_name": "",
                    "income_statement": {"financial_indicators": []},
                    "balance_sheet": {"financial_indicators": []},
                    "cash_flow_statement": {"financial_indicators": []},
                },
            ),
            "other": DocumentTypeConfig(
                name="其他",
                description="无法归入以上类型的文档",
                extraction_prompt="""该文档属于其他类型，不做业务字段提取，只返回空 JSON 对象。{common_rules}""",
                response_template={},
            ),
        },
    ),
}


def _document_type(name, description, response_template, extraction_rules):
    return DocumentTypeConfig(
        name=name,
        description=description,
        extraction_prompt=f"{extraction_rules}\n{{common_rules}}",
        response_template=response_template,
    )


def _classification_prompt(rules):
    return f"""### 分类识别判断规则
匹配优先级：文档名称、标题、封面名称 > 正文核心内容和典型字段。
每份文档只返回一个分类；冲突时以主标题、核心用途和核心内容为准。

候选类型：
{{type_options}}

{rules}

只返回合法 JSON：{{{{"document_type":"类型编码"}}}}，不得输出解释。
"""


_OTHER = BUSINESS_CONFIGS["0"].document_types["other"]
_FINANCIAL_REPORT = BUSINESS_CONFIGS["1"].document_types["financial_report"]
_PROJECT_REVIEW = BUSINESS_CONFIGS["1"].document_types["project_review_opinion"]
_PROPRIETARY_DUE_DILIGENCE = BUSINESS_CONFIGS["1"].document_types["proprietary_due_diligence"]

_TRUST_DUE_DILIGENCE = _document_type(
    "信托业务尽职调查报告",
    "信托业务尽职调查报告，包含项目基础信息、合规条款和退出路径",
    {
        "project_trust_name": "", "investigate_target": "", "investigate_date": "",
        "product_type": "", "risk_level": "", "target_company": "",
        "invest_appropriateness": "", "risk_isolation": "", "priority_subordinate": "",
        "difference_complement": "", "info_disclosure_support": "",
        "comply_regulation": "", "counterparty_rating": "", "exit_path": "",
    },
    "仅解析信托业务尽职调查报告。严格按固定结构摘录原文；不存在的字段返回空字符串。",
)

_CONTRACT_BASE = _document_type(
    "合同基础信息",
    "投资、保管、信托、借款或担保合同",
    {"base_indicators": []},
    "提取合同业务类型、业务类型、合同名称/编码、签订时间、期限、担保与还款方式、利率、资金来源、项目及信托计划名称、回购、对赌和违约条款。",
)
_PERPETUAL_BOND = _document_type(
    "永续债发行文件",
    "包含永续债清偿顺序、回售、赎回等条款的发行文件",
    {
        "project_name": "", "business_type": "", "transaction_parties": [],
        "invest_contract_code": "", "trust_contract_code": "", "trust_contract_name": "",
        "repayment_order": "", "has_investor_put_right": "",
        "has_issuer_call_right": "", "has_unconditional_principal_interest": "",
    },
    "仅解析永续债发行文件，提取项目、业务类型、交易主体、合同编号、清偿顺序及回售赎回权利。",
)
_MAJOR_RISK = _document_type(
    "项目重大风险信号报告单",
    "记录已发生逾期、违约或实质性重大风险事项的报告单",
    {
        "report_name": "", "report_date": "", "project_name": "",
        "belong_department": "", "risk_description": "", "handling_suggestion": "",
    },
    "仅解析重大风险信号报告单，完整摘录风险描述和处理建议。",
)
_PROJECT_ALERT = _document_type(
    "项目预警信号报告单",
    "记录潜在风险隐患、尚未形成实质违约的预警报告单",
    {
        "report_name": "", "report_date": "", "project_name": "",
        "belong_department": "", "risk_description": "", "handling_suggestion": "",
    },
    "仅解析项目预警信号报告单，完整摘录风险描述和处理建议。",
)
_POST_INVESTMENT_REPORT = _document_type(
    "信托项目投后报告",
    "信托财产管理报告或项目投后报告",
    {
        "project_name": "", "service_type": "", "establish_date": "",
        "outstanding_scale": "", "report_date": "", "risk_disclosure": "",
        "current_period_income": "", "year_to_date_income": "",
        "year_to_date_expense": "", "current_period_distributed_profit": "",
        "year_to_date_net_profit": "",
    },
    "仅解析信托项目投后报告；金额统一换算为元，提取项目基础信息、风险揭示和收支利润。",
)
_PAYMENT_ADVICE = _document_type(
    "信托项目付款通知单",
    "信托项目付款通知单",
    {"project_name": "", "contract_code": "", "payment_deadline": "", "total_payable_amount": ""},
    "仅解析付款通知单，提取项目名称、合同编号、付款截止日期和应付合计金额。",
)
_INFORMATION_DISCLOSURE = _document_type(
    "信息披露报告",
    "信托项目信息披露报告",
    {"project_name": "", "establish_time": "", "outstanding_scale": "", "trust_credit_rating": ""},
    "仅解析信息披露报告，提取项目名称、成立时间、存续规模和信用等级。",
)
_REQUEST_REPORT = _document_type(
    "信托项目请示报告",
    "信托项目请示报告",
    {"project_name": "", "establish_time": "", "project_type": "", "comply_asset_management_rule": ""},
    "仅解析信托项目请示报告，提取项目名称、成立时间、项目类型及资管新规合规结论。",
)
_DECISION_MEETING = _document_type(
    "项目决策委员会会议纪要",
    "包含议题、参会人员、审议事项、讨论意见和表决结果的会议纪要",
    {
        "topic_name": "", "review_time": "", "meeting_address": "", "meeting_form": "",
        "topic_content": "", "is_related_transaction": "", "vote_precondition": "",
        "vote_result": "", "meeting_member_list": [],
    },
    "仅解析项目决策委员会会议纪要，提取会议信息、议题、表决条件与结果，以及全部参会人员。",
)

_LEGAL_DOCUMENT_TYPES = {
    "investment_contract": _CONTRACT_BASE,
    "custody_agreement": _CONTRACT_BASE,
    "trust_contract": _CONTRACT_BASE,
    "loan_contract": _CONTRACT_BASE,
    "guarantee_contract": _CONTRACT_BASE,
    "perpetual_bond": _PERPETUAL_BOND,
    "financial_report": _FINANCIAL_REPORT,
    "other": _OTHER,
}

_PROPRIETARY_APPROVAL_PROMPT = _classification_prompt("""
1、项目评审意见书：标题含“项目评审意见书”，或正文包含项目编码、还款能力分析、担保能力分析、合规分析、风险等级、评审结论等项目风控审批、评审类核心内容。
2、固有业务尽调报告：标题含“固有”“固有业务”“尽调报告”“尽职调查报告”等关键词，针对固有业务出具，包含交易对手、业务、法律、风险、投资核查分析等尽调内容。
3、财务报告：以企业合并资产负债表、利润表、现金流量表为核心，包含标准化多期财务数据；仅附带少量财务数据的文件不归入此类。
4、其他：无法匹配以上三类标准的文件。
""")

_TRUST_APPROVAL_PROMPT = _classification_prompt("""
1、项目评审意见书：标题含“项目评审意见书”，或正文包含项目编码、还款能力分析、担保能力分析、合规分析、风险等级、评审结论等项目风控审批、评审类核心内容。
2、信托业务尽调报告：标题含“信托业务尽调报告”“尽调报告”“尽职调查报告”等关键词，包含调查对象、产品类型、风险等级、投资适当性、风险隔离、优先/劣后级、差额补足、信息披露、资管新规和退出路径等内容。
3、财务报告：以企业合并资产负债表、利润表、现金流量表为核心，包含标准化多期财务数据；仅附带少量财务数据的文件不归入此类。
4、其他：无法匹配以上三类标准的文件。
""")

_LEGAL_REVIEW_PROMPT = _classification_prompt("""
投资协议合同：信托、固有业务对外股权投资、债权投资通用协议文件；不含永续债、借款、保管、信托份额相关合同。
保管协议：信托资金托管、财产保管服务配套签署的协议。
信托合同：投资者与信托机构签署，用于认购信托份额的合同文件或固有资金签订的投资合同。
借款合同：信托方向融资主体发放贷款所对应的借贷类合同。
担保合同：为提供担保服务的合同文件。
永续债发行文件：标题或正文包含“永续债”，约定清偿顺序、回售、强制赎回等永续债特有条款的全套发行、投资协议文件。
财务报告：附带企业合并资产负债表、利润表、现金流量表，以标准化多期财务报表为核心的专项文件；仅零散附带少量财务数据的非专项文件不归入此类。
其他：无法匹配以上类型的文档。

注意：如果文件的业务类型为永续债则优先匹配为永续债，不论其属于合同、协议、报告还是其他文件。
""")

_RISK_SIGNAL_PROMPT = _classification_prompt("""
1、项目重大风险信号报告单：记录项目已发生逾期、债务违约、实质性重大风险事项的内部上报单据。
2、项目预警信号报告单：风控指标触发阈值、存在潜在风险隐患，尚未形成实质违约的风险预警上报单据。
3、其他：无法匹配以上两类标准的文档。
""")

_FINANCIAL_ONLY_PROMPT = _classification_prompt("""
1、财务报告：附带企业合并资产负债表、利润表、现金流量表，以标准化多期财务报表为核心的专项文件；仅零散附带少量财务数据的非专项文件不归入此类。
2、其他：无法匹配财务报告标准的文档。
""")

_DISCLOSURE_PROMPT = _classification_prompt("""
1、信托项目投后报告：信托财产管理报告或项目投后报告，包含项目成立、存续规模、运营收支、利润和风险揭示等信息。
2、信托项目付款通知单：围绕项目付款，包含合同编号、付款截止日期、收付款账户或应付合计金额等信息。
3、信息披露报告：面向信托项目的信息披露文件，包含成立时间、存续规模、项目状态或信用等级等信息。
4、信托项目请示报告：围绕信托项目设立、变更或审批事项形成的请示报告，包含项目类型、合规性和请示事项。
5、其他：无法匹配以上四类标准的文档。
""")

_MEETING_PROMPT = _classification_prompt("""
1、决策会议纪要：包含会议议题、参会人员、审议事项、讨论意见、表决前提条件、表决结果等要素的各类项目评审、投决会议记录文件。
2、其他：无法匹配决策会议纪要标准的文档。
""")

# 原始工作流判断器中的 12 个 business_code。编码保持原样，避免调用方再做二次映射。
BUSINESS_CONFIGS = {
    "0": BUSINESS_CONFIGS["0"],
    "t825528fb58c11e89611c85b76568133": BusinessConfig(
        classification_prompt=_PROPRIETARY_APPROVAL_PROMPT,
        document_types={
            "project_review_opinion": _PROJECT_REVIEW,
            "proprietary_due_diligence": _PROPRIETARY_DUE_DILIGENCE,
            "financial_report": _FINANCIAL_REPORT,
            "other": _OTHER,
        },
    ),
    "v76ce68f9ad411e883d900505688bf34": BusinessConfig(
        classification_prompt=_TRUST_APPROVAL_PROMPT,
        document_types={
            "project_review_opinion": _PROJECT_REVIEW,
            "trust_due_diligence": _TRUST_DUE_DILIGENCE,
            "financial_report": _FINANCIAL_REPORT,
            "other": _OTHER,
        },
    ),
    "q762eff6134f11ef886600505688bf63": BusinessConfig(
        classification_prompt=_LEGAL_REVIEW_PROMPT,
        document_types=_LEGAL_DOCUMENT_TYPES,
    ),
    "oa73358cd24d11efaf24005056889512": BusinessConfig(
        classification_prompt=_LEGAL_REVIEW_PROMPT,
        document_types=_LEGAL_DOCUMENT_TYPES,
    ),
    "p0d1086cee7911eab64d005056882405": BusinessConfig(
        classification_prompt=_RISK_SIGNAL_PROMPT,
        document_types={"major_risk": _MAJOR_RISK, "project_alert": _PROJECT_ALERT, "other": _OTHER},
    ),
    "tad9b5a6f33011ea88a4005056882405": BusinessConfig(
        classification_prompt=_RISK_SIGNAL_PROMPT,
        document_types={"major_risk": _MAJOR_RISK, "project_alert": _PROJECT_ALERT, "other": _OTHER},
    ),
    "sbbceccf1c3011e7816d8fafc29309c7": BusinessConfig(
        classification_prompt=_FINANCIAL_ONLY_PROMPT,
        document_types={"financial_report": _FINANCIAL_REPORT, "other": _OTHER},
    ),
    "f7a140b0b33c11e8856bc85b76568133": BusinessConfig(
        classification_prompt=_FINANCIAL_ONLY_PROMPT,
        document_types={"financial_report": _FINANCIAL_REPORT, "other": _OTHER},
    ),
    "oef141d87c0d11f19fd45254a56cb8df": BusinessConfig(
        classification_prompt=_DISCLOSURE_PROMPT,
        document_types={
            "post_investment_report": _POST_INVESTMENT_REPORT,
            "payment_advice": _PAYMENT_ADVICE,
            "information_disclosure": _INFORMATION_DISCLOSURE,
            "request_report": _REQUEST_REPORT,
            "other": _OTHER,
        },
    ),
    "p4cfd7c6abf611e88d4400505688f972": BusinessConfig(
        classification_prompt=_MEETING_PROMPT,
        document_types={"decision_meeting_minutes": _DECISION_MEETING, "other": _OTHER},
    ),
    "e85e068fb34d11e8bacbc85b76568133": BusinessConfig(
        classification_prompt=_MEETING_PROMPT,
        document_types={"decision_meeting_minutes": _DECISION_MEETING, "other": _OTHER},
    ),
}


class DocumentProcessingError(Exception):
    """可安全返回给接口调用方的处理错误。"""


class UnsupportedBusinessCodeError(DocumentProcessingError):
    pass


class UnconfiguredBusinessCodeError(DocumentProcessingError):
    pass


class LLMResponseError(DocumentProcessingError):
    pass


def _to_text(data: Any) -> str:
    if data is None:
        raise DocumentProcessingError("data 不能为空")
    text = data.strip() if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    if not text:
        raise DocumentProcessingError("data 不能为空")
    return text


def _parse_json_object(content: str) -> Dict[str, Any]:
    value = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, re.S | re.I)
    if fenced:
        value = fenced.group(1)
    else:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            value = value[start:end + 1]
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LLMResponseError("大模型未返回合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseError("大模型返回值必须是 JSON 对象")
    return parsed


def _fixed_response(result: Mapping[str, Any], template: Mapping[str, Any]) -> Dict[str, Any]:
    """过滤多余字段、补齐缺失字段，并拒绝错误的数据类型。"""
    output = {}
    for field, default in template.items():
        value = result.get(field, copy.deepcopy(default))
        if not isinstance(value, type(default)):
            raise LLMResponseError(
                f"字段 {field} 类型错误，应为 {type(default).__name__}，实际为 {type(value).__name__}"
            )
        output[field] = value
    return output


class DocumentProcessor:
    def __init__(self, model_url=None, model_key=None, model_name=None, client=None):
        self.model_url = model_url or config.MODEL_URL
        self.model_key = model_key or config.MODEL_KEY
        self.model_name = model_name or getattr(config, "DOCUMENT_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")
        self.client: httpx.AsyncClient = client

    async def _chat(self, system_prompt: str, user_text: str) -> Dict[str, Any]:
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        }
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.model_key}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=120.0)
        try:
            response = await client.post(self.model_url, headers=headers, json=payload)
            response.raise_for_status()
            return _parse_json_object(response.json()["choices"][0]["message"]["content"])
        except DocumentProcessingError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMResponseError(f"大模型调用或响应解析失败: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

    def _business_config(self, business_code: str) -> BusinessConfig:
        code = business_code.strip()
        business = BUSINESS_CONFIGS.get(code)
        if business is None:
            raise UnsupportedBusinessCodeError(
                f"不支持的 business_code: {business_code}；当前支持: {', '.join(sorted(BUSINESS_CONFIGS))}"
            )
        if not business.classification_prompt.strip() or not business.document_types:
            raise UnconfiguredBusinessCodeError(f"business_code {code} 尚未配置分类和取数规则")
        return business

    async def classify(self, text: str, business: BusinessConfig) -> str:
        options = "\n".join(
            f"- {code}: {item.name}；{item.description}"
            for code, item in business.document_types.items()
        )
        result = await self._chat(business.classification_prompt.format(type_options=options), text)
        document_type = result.get("document_type")
        if document_type not in business.document_types:
            raise LLMResponseError(f"大模型返回了非法具体类型: {document_type}")
        return document_type

    async def extract(self, text: str, type_config: DocumentTypeConfig) -> Dict[str, Any]:
        common_rules = COMMON_EXTRACTION_RULES.format(
            response_template=json.dumps(type_config.response_template, ensure_ascii=False, indent=2)
        )
        prompt = type_config.extraction_prompt.format(common_rules=common_rules)
        return _fixed_response(await self._chat(prompt, text), type_config.response_template)

    async def process(
        self, business_code: str, data: Any
    ) -> Tuple[str, DocumentTypeConfig, Dict[str, Any]]:
        text = _to_text(data)
        business = self._business_config(business_code)
        document_type = await self.classify(text, business)
        type_config = business.document_types[document_type]
        extracted = await self.extract(text, type_config)
        return document_type, type_config, extracted
