import sys
import os
from dotenv import load_dotenv

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

# Import scanner logic
from scanner import scan_gitlab_repo, score_risk_with_gemini, generate_report, _demo_findings, generate_code_patch

if __name__ == "__main__":
    load_dotenv()
    
    print("🛡️  NHI Governance Agent (CLI)")
    print("========================\n")

    repo_url     = input("Enter GitLab repo URL (or 'demo'): ")
    gitlab_token = input("Enter GitLab token (or press Enter to skip): ").strip()

    nhis   = scan_gitlab_repo(repo_url, gitlab_token if gitlab_token else None)
    scored = score_risk_with_gemini(nhis)
    generate_report(scored)

    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        try:
            from db import save_scan
            scan_id = save_scan(repo_url, scored)
            print(f"\n💾 Saved to MongoDB — scan ID: {scan_id}")
        except Exception as e:
            print(f"\n⚠️  MongoDB save skipped: {e}")
    else:
        print("\n💡 Set MONGO_URI in .env to persist findings.")
