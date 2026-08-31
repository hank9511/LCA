import openai
import json
from typing import Dict, List, Optional, Tuple

STANDARD_LIFECYCLE_STAGES = {
    "overall": {
        "name": "总体环节",
        "description": "代表整个产品生命周期的系统级过程，不属于单一环节",
        "keywords": [
            "life cycle",
            "lifecycle",
            "system",
            "overall",
            "total",
            "complete",
            "entire",
            "whole",
            "全生命周期",
            "整体",
            "系统",
            "总体",
        ],
    },
    "raw_material": {
        "name": "原材料获取",
        "description": "包括原材料的开采、提取、初加工等活动",
        "keywords": [
            "开采",
            "提取",
            "采矿",
            "林业",
            "农业",
            "原料",
            "矿石",
            "木材",
            "石油",
            "天然气",
        ],
    },
    "production": {
        "name": "生产制造",
        "description": "产品的加工、制造、组装等生产活动",
        "keywords": [
            "生产",
            "制造",
            "加工",
            "组装",
            "合成",
            "成型",
            "铸造",
            "锻造",
            "焊接",
            "注塑",
        ],
    },
    "transport": {
        "name": "运输配送",
        "description": "产品或物料的运输、物流、配送活动",
        "keywords": [
            "运输",
            "物流",
            "配送",
            "交通",
            "货运",
            "船运",
            "空运",
            "铁路",
            "公路",
        ],
    },
    "use": {
        "name": "使用阶段",
        "description": "产品在使用过程中的能源消耗、维护等活动",
        "keywords": ["使用", "运行", "操作", "维护", "保养", "消耗", "电力", "燃料"],
    },
    "disposal": {
        "name": "废弃处理",
        "description": "产品废弃后的处理、处置活动,如填埋、焚烧等",
        "keywords": ["废弃", "处理", "处置", "填埋", "焚烧", "垃圾", "废物", "销毁"],
    },
    "recycling": {
        "name": "回收再利用",
        "description": "产品或材料的回收、再生、循环利用活动",
        "keywords": ["回收", "再生", "循环", "重复使用", "再制造", "翻新", "回用"],
    },
}


def match_lifecycle_stage_with_llm(
    process_names: List[str], api_key: str
) -> Dict[str, Dict]:

    try:

        client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

        stages_desc = "\n".join(
            [
                f"- {key}: {info['name']} - {info['description']}"
                for key, info in STANDARD_LIFECYCLE_STAGES.items()
            ]
        )

        processes_list = "\n".join(
            [f"{i+1}. {name}" for i, name in enumerate(process_names)]
        )

        prompt = f"""你是一个专业的LCA(生命周期评估)专家。请为以下过程匹配最合适的生命周期环节。

可选的生命周期环节:
{stages_desc}

需要匹配的过程列表:
{processes_list}

请以JSON格式返回结果,格式如下:
{{
    "matches": [
        {{
            "process": "过程名称",
            "stage": "环节代码(如raw_material)",
            "confidence": 0.95,
            "reasoning": "匹配理由"
        }}
    ]
}}

要求:
1. confidence是0-1之间的小数,表示匹配的置信度
2. reasoning简要说明为什么选择这个环节
3. 每个过程必须匹配一个环节
4. 只返回JSON,不要返回其他文本
"""

        response = client.chat.completions.create(
            model="x-ai/grok-3-mini",
            messages=[
                {
                    "role": "system",
                    "content": "你是专业的LCA专家,请准确地为过程匹配生命周期环节。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4000,
            stream=False,
        )

        response_text = response.choices[0].message.content.strip()

        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        result = json.loads(response_text)

        matches_dict = {}
        for match in result.get("matches", []):
            process = match.get("process")
            if process in process_names:
                matches_dict[process] = {
                    "stage": match.get("stage"),
                    "confidence": match.get("confidence", 0.5),
                    "reasoning": match.get("reasoning", ""),
                }

        return matches_dict

    except Exception as e:
        print(f"LLM matching error: {e}")

        raise


def fallback_rule_based_matching(process_names: List[str]) -> Dict[str, Dict]:

    matches = {}

    for process in process_names:
        process_lower = process.lower()
        matched_stage = "production"
        confidence = 0.3
        reasoning = "基于规则的默认匹配"

        max_score = 0
        for stage_key, stage_info in STANDARD_LIFECYCLE_STAGES.items():
            score = 0
            matched_keywords = []
            for keyword in stage_info["keywords"]:
                if keyword in process_lower:
                    score += 1
                    matched_keywords.append(keyword)

            if score > max_score:
                max_score = score
                matched_stage = stage_key
                if matched_keywords:
                    confidence = min(0.7, 0.3 + score * 0.1)
                    reasoning = f"包含关键词: {', '.join(matched_keywords)}"
                else:
                    confidence = 0.3
                    reasoning = "基于规则的默认匹配"

        matches[process] = {
            "stage": matched_stage,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    return matches


def get_lifecycle_stage_info(stage_key: str) -> Optional[Dict]:

    return STANDARD_LIFECYCLE_STAGES.get(stage_key)


def get_all_lifecycle_stages() -> Dict:

    return STANDARD_LIFECYCLE_STAGES
