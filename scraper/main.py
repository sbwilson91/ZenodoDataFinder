# scraper/main.py
import os
from datetime import datetime
from .feeds import load_config, fetch_papers
from .extract_repos import extract_all_repos
from .summarise import summarise_papers
from .report import generate_report, update_archive_index

def main():
    config    = load_config()
    hf_token  = os.environ["HF_API_TOKEN"]   # Set in GitHub Actions secrets

    print("Step 1/4: Fetching papers from RSS feeds...")
    papers = fetch_papers(config)

    if not papers:
        print("No new papers found this week. Exiting.")
        return

    print("\nStep 2/4: Extracting repository links from abstracts...")
    extract_all_repos(papers)

    print("\nStep 3/4: Generating summaries via HuggingFace Inference API...")
    papers = summarise_papers(papers, hf_token=hf_token)

    date_str     = datetime.now().strftime("%Y-%m-%d")
    output_path  = f"digests/{date_str}-weekly-digest.md"

    

    print(f"\nStep 4/4: Building report → {output_path}")
    os.makedirs("digests", exist_ok=True)
    generate_report(papers, config, output_path)
    update_archive_index(output_path, paper_count=len(papers))
    print(f"  Done. Digest: {output_path}")

    print("\n✓ Done.")

if __name__ == "__main__":
    main()
