import re

from core.config import get_preferred_location_keywords, get_preferred_role_keywords


def normalize_text(value):
    return re.sub(r"\s+", " ", value.lower()).strip()


def count_keyword_hits(text, keywords):
    normalized = normalize_text(text)
    hits = []
    for keyword in keywords:
        lowered = normalize_text(keyword)
        if lowered and lowered in normalized:
            hits.append(keyword)
    return hits


def extract_resume_keywords(resume_text):
    candidate_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9\+#\.\-/]{2,}", resume_text.lower())
    stopwords = {
        "with", "from", "that", "this", "have", "your", "will", "team", "role", "years", "using",
        "into", "such", "than", "their", "about", "work", "data", "engineer", "manager", "senior",
    }
    ranked_terms = []
    seen = set()
    for term in candidate_terms:
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        ranked_terms.append(term)
        if len(ranked_terms) >= 40:
            break
    return ranked_terms


def score_job_context(job_context, resume_text, candidate_profile):
    combined_text = "\n".join(
        [job_context["page_title"], job_context["job_title"], job_context["description"], job_context["page_text"][:3000]]
    )
    score = 0
    reasons = []

    role_hits = count_keyword_hits(combined_text, get_preferred_role_keywords())
    if role_hits:
        score += 25 * len(role_hits)
        reasons.append(f"role matches: {', '.join(role_hits[:4])}")

    location_hits = count_keyword_hits(combined_text, get_preferred_location_keywords(candidate_profile))
    if location_hits:
        score += 12 * len(location_hits)
        reasons.append(f"location matches: {', '.join(location_hits[:3])}")

    resume_hits = count_keyword_hits(combined_text, extract_resume_keywords(resume_text))
    if resume_hits:
        score += min(len(resume_hits), 10) * 4
        reasons.append(f"resume overlap: {', '.join(resume_hits[:5])}")

    eligibility_markers = (
        "green card",
        "u.s. citizens",
        "citizens only",
        "no sponsorship",
        "no opt",
    )
    eligibility_hits = count_keyword_hits(combined_text, list(eligibility_markers))
    if candidate_profile["sponsorship_needed"].strip().lower() == "no" and eligibility_hits:
        score += 10
        reasons.append("eligibility aligned")

    if job_context.get("verified"):
        score += 30
        reasons.append(f"verified via {job_context.get('verification_source')}")

    return score, reasons


def extract_priority_job_keywords(job_context):
    combined_text = "\n".join(
        [job_context.get("job_title", ""), job_context.get("description", ""), job_context.get("page_text", "")[:4000]]
    ).lower()
    candidate_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9\+#\./-]{2,}", combined_text)
    stopwords = {
        "with", "from", "that", "this", "have", "your", "will", "team", "role", "years", "using",
        "into", "such", "than", "their", "about", "work", "data", "engineer", "manager", "senior",
        "experience", "required", "preferred", "strong", "including", "support", "design", "build",
    }
    keywords = []
    seen = set()
    for term in candidate_terms:
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        keywords.append(term)
        if len(keywords) >= 60:
            break
    return keywords


def analyze_resume_gaps(job_context, resume_text, candidate_profile):
    job_keywords = extract_priority_job_keywords(job_context)
    resume_keywords = set(extract_resume_keywords(resume_text))
    preferred_roles = [normalize_text(item) for item in get_preferred_role_keywords()]

    matched_keywords = [keyword for keyword in job_keywords if normalize_text(keyword) in resume_keywords][:15]
    missing_keywords = [keyword for keyword in job_keywords if normalize_text(keyword) not in resume_keywords][:15]
    role_matches = [keyword for keyword in preferred_roles if keyword and keyword in normalize_text(job_context.get("page_text", ""))]

    readiness = "strong"
    if len(missing_keywords) >= 10:
        readiness = "medium"
    if len(missing_keywords) >= 14:
        readiness = "stretch"

    return {
        "readiness": readiness,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "role_matches": role_matches,
        "candidate_location": candidate_profile.get("location"),
    }


def render_gap_analysis_markdown(job_context, gap_analysis):
    matched = ", ".join(gap_analysis["matched_keywords"][:10]) or "No strong overlap detected"
    missing = ", ".join(gap_analysis["missing_keywords"][:10]) or "No major missing keywords detected"
    role_matches = ", ".join(gap_analysis["role_matches"][:6]) or "No preferred-role keyword matches recorded"
    return (
        "# Resume Gap Analysis\n\n"
        f"## Role\n- Company: {job_context['company_name']}\n- Title: {job_context['job_title']}\n- Readiness: {gap_analysis['readiness']}\n\n"
        f"## Current Matches\n- {matched}\n\n"
        f"## Likely Gaps To Prepare\n- {missing}\n\n"
        f"## Role Alignment Signals\n- {role_matches}\n"
    )


def render_follow_up_markdown(job_context, candidate_profile):
    recruiter_message = (
        f"Hi, I recently applied for the {job_context['job_title']} role at {job_context['company_name']}. "
        "My background includes Snowflake, SQL, ETL, and production data-platform support, and I would welcome the chance "
        "to discuss how I can contribute. Thank you for your time."
    )
    email_message = (
        f"Subject: Application Follow-Up - {job_context['job_title']}\n\n"
        f"Hello {job_context['company_name']} team,\n\n"
        f"I applied for the {job_context['job_title']} position and wanted to follow up with continued interest. "
        f"I bring experience in database and data-platform engineering, including Snowflake, SQL, ETL, automation, and production support. "
        "If helpful, I would be glad to discuss my background further.\n\n"
        f"Best regards,\n{candidate_profile['first_name']} {candidate_profile['last_name']}\n{candidate_profile['email']}\n{candidate_profile['phone']}"
    )
    return (
        "# Recruiter Follow-Up Pack\n\n"
        "## LinkedIn Message\n"
        f"{recruiter_message}\n\n"
        "## Email Follow-Up\n"
        f"```text\n{email_message}\n```\n"
    )


def print_ranked_job_summary(ranked_jobs, selection_count):
    print(f"[*] Ranked {len(ranked_jobs)} jobs. Selecting top {selection_count} verified postings.")
    for index, item in enumerate(ranked_jobs[:selection_count], start=1):
        context = item["job_context"]
        reason_text = "; ".join(item["reasons"][:3]) if item["reasons"] else "no scoring reasons"
        print(
            f"[{index}] score={item['score']} | {context.get('company_name')} | {context.get('job_title')} | {reason_text}"
        )
