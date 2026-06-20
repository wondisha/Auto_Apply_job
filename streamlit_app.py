import subprocess
import sys
from pathlib import Path

import streamlit as st

from apply_agent import (
    ARTIFACTS_ROOT,
    get_candidate_profile,
    list_recent_application_events,
    load_question_memory,
    load_job_urls,
    preview_ranked_jobs,
    save_question_memory,
)


st.set_page_config(page_title="Auto Apply Job", layout="wide")


APP_ROOT = Path(__file__).resolve().parent


def run_cli_command(arguments):
    command = [sys.executable, str(APP_ROOT / "apply_agent.py"), *arguments]
    completed = subprocess.run(
        command,
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
    )
    return completed, command


def render_command_result(result, command):
    st.code(" ".join(command), language="powershell")
    if result.returncode == 0:
        st.success("Command completed successfully.")
    else:
        st.error(f"Command failed with exit code {result.returncode}.")

    if result.stdout.strip():
        st.text_area("Standard output", result.stdout, height=240)
    if result.stderr.strip():
        st.text_area("Standard error", result.stderr, height=180)


def render_dashboard():
    st.subheader("Recent Applications")
    events = list_recent_application_events(limit=50)
    if not events:
        st.info("No structured application events recorded yet.")
        return

    table_rows = []
    for event in events:
        table_rows.append(
            {
                "Timestamp": event["timestamp"],
                "Status": event["status"],
                "Company": event["company_name"],
                "Role": event["job_title"],
                "Verified": "Yes" if event["verified"] else "No",
                "Reason": event["reason"] or "",
            }
        )
    st.dataframe(table_rows, use_container_width=True)


def render_discovery():
    st.subheader("Discover and Rank Jobs")
    default_resume = str((Path(__file__).with_name("wondi.pdf")).resolve())
    query = st.text_input("Job search query", value="data engineer")
    location = st.text_input("Location", value="Texas")
    resume_path = st.text_input("Resume path", value=default_resume)

    if st.button("Preview ranked jobs"):
        try:
            job_urls = load_job_urls(None, None, job_search_query=query, job_search_location=location, job_search_portal="linkedin")
            success = preview_ranked_jobs(job_urls, resume_path)
            if success:
                st.success(f"Discovered and ranked {len(job_urls)} jobs. Check the terminal output for detailed ranking reasons.")
            else:
                st.warning("No verified jobs qualified in the ranked preview.")
        except Exception as exc:
            st.error(str(exc))


def render_documents():
    st.subheader("Generate Prep Pack")
    default_resume = str((Path(__file__).with_name("wondi.pdf")).resolve())
    job_url = st.text_input("Job URL", value="https://www.linkedin.com/jobs/view/senior-data-engineer-at-hcltech-4414046431")
    resume_path = st.text_input("Resume path", value=default_resume, key="docs_resume_path")

    if st.button("Generate artifacts"):
        try:
            result, command = run_cli_command(["--generate-docs-only", "--job-url", job_url, "--resume", resume_path])
            render_command_result(result, command)
            st.caption(f"Artifacts root: {ARTIFACTS_ROOT}")
        except Exception as exc:
            st.error(str(exc))


def render_run_controls():
    st.subheader("Run Application Flows")
    default_resume = str((Path(__file__).with_name("wondi.pdf")).resolve())
    single_job_url = st.text_input(
        "Single job URL",
        value="https://www.linkedin.com/jobs/view/senior-data-engineer-at-hcltech-4414046431",
    )
    batch_file = st.text_input("Batch file path", value=str((APP_ROOT / "jobs.txt").resolve()))
    resume_path = st.text_input("Resume path", value=default_resume, key="run_resume_path")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Run preflight"):
            result, command = run_cli_command(["--preflight", "--job-url", single_job_url, "--resume", resume_path])
            render_command_result(result, command)
    with col2:
        if st.button("Apply single job"):
            result, command = run_cli_command(["--job-url", single_job_url, "--resume", resume_path])
            render_command_result(result, command)
    with col3:
        if st.button("Run batch apply"):
            result, command = run_cli_command(["--job-urls-file", batch_file, "--resume", resume_path])
            render_command_result(result, command)


def render_question_memory():
    st.subheader("Screening Answer Memory")
    current_memory = load_question_memory()
    if current_memory:
        st.dataframe(
            [
                {"Question": item["question"], "Answer": item["answer"], "Source": item["source"], "Updated": item["updated_at"]}
                for item in sorted(current_memory.values(), key=lambda entry: entry["question"].lower())
            ],
            use_container_width=True,
        )
    else:
        st.info("No saved screening answers yet.")

    with st.form("question_memory_form"):
        question = st.text_input("Question")
        answer = st.text_input("Answer")
        submitted = st.form_submit_button("Save answer")
        if submitted:
            if not question.strip() or not answer.strip():
                st.error("Question and answer are required.")
            else:
                save_question_memory(question, answer, source="streamlit-app")
                st.success("Saved screening answer.")


def render_candidate_profile():
    st.subheader("Candidate Profile Snapshot")
    st.json(get_candidate_profile())


st.title("Auto Apply Job App")
st.caption("Lightweight dashboard for discovery, prep generation, application history, and screening-answer memory.")

dashboard_tab, discovery_tab, docs_tab, run_tab, memory_tab, profile_tab = st.tabs(
    ["Dashboard", "Discover", "Prep Pack", "Run", "Question Memory", "Profile"]
)

with dashboard_tab:
    render_dashboard()

with discovery_tab:
    render_discovery()

with docs_tab:
    render_documents()

with run_tab:
    render_run_controls()

with memory_tab:
    render_question_memory()

with profile_tab:
    render_candidate_profile()