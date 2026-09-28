import openai
import json
from typing import Dict, List, Optional, Tuple

STANDARD_LIFECYCLE_STAGES = {
    "overall": {
        "name": "Overall stage",
        "description": "System-level process representing the entire product life cycle, not belonging to a single stage",
        "keywords": [
            "life cycle",
            "lifecycle",
            "system",
            "overall",
            "total",
            "complete",
            "entire",
            "whole",
        ],
    },
    "raw_material": {
        "name": "Raw material acquisition",
        "description": "Includes raw material extraction, mining, and primary processing activities",
        "keywords": [
            "extraction",
            "extract",
            "mining",
            "forestry",
            "agriculture",
            "feedstock",
            "ore",
            "timber",
            "petroleum",
            "natural gas",
        ],
    },
    "production": {
        "name": "Manufacturing",
        "description": "Product processing, manufacturing, assembly, and other production activities",
        "keywords": [
            "production",
            "manufacturing",
            "processing",
            "assembly",
            "synthesis",
            "forming",
            "casting",
            "forging",
            "welding",
            "injection molding",
        ],
    },
    "transport": {
        "name": "Transport and distribution",
        "description": "Transport, logistics, and distribution of products or materials",
        "keywords": [
            "transport",
            "logistics",
            "distribution",
            "traffic",
            "freight",
            "shipping",
            "air freight",
            "rail",
            "road",
        ],
    },
    "use": {
        "name": "Use stage",
        "description": "Energy consumption, maintenance, and related activities during product use",
        "keywords": [
            "use",
            "operation",
            "operate",
            "maintenance",
            "upkeep",
            "consumption",
            "electricity",
            "fuel",
        ],
    },
    "disposal": {
        "name": "End-of-life treatment",
        "description": "Treatment and disposal after product discard, such as landfill or incineration",
        "keywords": [
            "disposal",
            "treatment",
            "landfill",
            "incineration",
            "waste",
            "refuse",
            "destruction",
        ],
    },
    "recycling": {
        "name": "Recycling and reuse",
        "description": "Recovery, regeneration, and recycling of products or materials",
        "keywords": [
            "recycling",
            "recovery",
            "regeneration",
            "circular",
            "reuse",
            "remanufacturing",
            "refurbishment",
        ],
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

        prompt = f"""You are a professional LCA (Life Cycle Assessment) expert. Match each process below to the most appropriate life-cycle stage.

Available life-cycle stages:
{stages_desc}

Processes to match:
{processes_list}

Return the result in JSON with this format:
{{
    "matches": [
        {{
            "process": "process name",
            "stage": "stage code (e.g. raw_material)",
            "confidence": 0.95,
            "reasoning": "matching rationale"
        }}
    ]
}}

Requirements:
1. confidence is a decimal between 0 and 1 indicating match confidence
2. reasoning briefly explains why this stage was chosen
3. every process must be matched to one stage
4. return JSON only, with no other text
"""

        response = client.chat.completions.create(
            model="x-ai/grok-3-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional LCA expert. Accurately match processes to life-cycle stages.",
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
        reasoning = "Rule-based default match"

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
                    reasoning = f"Contains keywords: {', '.join(matched_keywords)}"
                else:
                    confidence = 0.3
                    reasoning = "Rule-based default match"

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
