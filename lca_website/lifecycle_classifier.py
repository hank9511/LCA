def classify_lifecycle_stage(process_name):

    if not process_name:
        return "production"

    name_lower = process_name.lower()

    overall_keywords = [
        "life cycle",
        "lifecycle",
        "lca",
        "cradle to grave",
        "cradle-to-grave",
        "system",
        "overall",
        "total",
        "complete",
        "entire",
        "whole system",
        "product system",
        "full cycle",
        "end to end",
        "end-to-end",
        "life cycle",
        "overall",
        "system",
        "total",
        "complete",
        "whole process",
    ]

    raw_material_keywords = [
        "extraction",
        "mining",
        "quarry",
        "crude",
        "ore",
        "raw material",
        "cultivation",
        "forestry",
        "agriculture",
        "harvest",
        "drilling",
        "natural gas",
        "petroleum",
        "coal mine",
        "iron ore",
        "bauxite",
        "limestone",
        "gravel",
        "sand",
        "clay",
        "wood production",
        "cotton",
        "primary",
        "virgin",
        "fresh water",
        "groundwater",
    ]

    production_keywords = [
        "production",
        "manufacturing",
        "processing",
        "factory",
        "plant",
        "refining",
        "smelting",
        "casting",
        "forging",
        "welding",
        "assembly",
        "fabrication",
        "synthesis",
        "chemical",
        "reaction",
        "injection molding",
        "extrusion",
        "rolling",
        "machining",
        "blown film",
        "forming",
        "cutting",
        "market for",
    ]

    transport_keywords = [
        "transport",
        "freight",
        "truck",
        "lorry",
        "ship",
        "train",
        "cargo",
        "delivery",
        "distribution",
        "logistic",
        "vehicle",
        "rail",
        "sea",
        "ocean",
        "air freight",
        "pipeline",
        "transoceanic",
        "container",
        "bulk",
        "tanker",
    ]

    use_keywords = [
        "electricity",
        "energy",
        "heat",
        "steam",
        "power",
        "fuel",
        "heating",
        "cooling",
        "lighting",
        "at user",
        "at grid",
        "at consumer",
        "consumption",
        "operation",
        "maintenance",
        "service",
    ]

    disposal_keywords = [
        "disposal",
        "waste",
        "landfill",
        "incineration",
        "treatment",
        "wastewater",
        "sewage",
        "effluent",
        "emission",
        "discharge",
        "end-of-life",
        "demolition",
        "dismantling",
        "scrap",
        "municipal solid waste",
        "hazardous waste",
    ]

    recycling_keywords = [
        "recycling",
        "recycle",
        "recovery",
        "reuse",
        "reclaimed",
        "regeneration",
        "reprocessing",
        "secondary",
        "from waste",
        "recovered",
        "recondition",
        "refurbish",
        "compost",
    ]

    keyword_rules = [
        ("overall", overall_keywords),
        ("recycling", recycling_keywords),
        ("disposal", disposal_keywords),
        ("transport", transport_keywords),
        ("use", use_keywords),
        ("raw_material", raw_material_keywords),
        ("production", production_keywords),
    ]

    for stage, keywords in keyword_rules:
        for keyword in keywords:
            if keyword in name_lower:
                return stage

    return "production"


def get_stage_confidence(process_name):

    if not process_name:
        return 0.3

    name_lower = process_name.lower()

    high_confidence_patterns = [
        "life cycle",
        "lifecycle",
        "lca",
        "cradle to grave",
        "recycling",
        "recycle",
        "disposal",
        "waste treatment",
        "transport",
        "freight",
        "electricity production",
        "mining",
        "extraction",
        "crude oil",
        "natural gas",
        "life cycle",
        "overall",
        "system",
    ]

    medium_confidence_patterns = [
        "production",
        "manufacturing",
        "processing",
        "operation",
        "use",
        "energy",
        "market for",
    ]

    for pattern in high_confidence_patterns:
        if pattern in name_lower:
            return 0.9

    for pattern in medium_confidence_patterns:
        if pattern in name_lower:
            return 0.7

    return 0.5


def classify_with_details(process_name):

    stage = classify_lifecycle_stage(process_name)
    confidence = get_stage_confidence(process_name)

    reasoning = f"Based on process name keyword analysis, inferred as '{stage}' stage"

    return {"stage": stage, "confidence": confidence, "reasoning": reasoning}


if __name__ == "__main__":

    test_cases = [
        "Electricity, medium voltage, production UCTE, at grid",
        "Transport, freight, lorry >16t, fleet average",
        "Disposal, municipal solid waste, 22.9% water, to sanitary landfill",
        "Aluminium, primary, ingot, IAI Area, RNA, at plant",
        "Crude oil, at production/NG",
        "Injection moulding, part 50g, part 60mm x 60mm x 4mm",
        "Recycling aluminium, from new scrap",
        "Electricity, high voltage, at grid",
    ]

    print("Life cycle stage intelligent classification test:\n")
    for test_name in test_cases:
        result = classify_with_details(test_name)
        print(f"Process: {test_name}")
        print(f"  → Stage: {result['stage']}")
        print(f"  → Confidence: {result['confidence']:.2f}")
        print(f"  → Reasoning: {result['reasoning']}\n")
