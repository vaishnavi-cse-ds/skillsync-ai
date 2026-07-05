import os
import sys
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("skillsync_mcp_server")

@mcp.tool()
def fetch_github_profile(username: str) -> dict:
    """Fetches key developer statistics and metadata for a given GitHub username.

    Args:
        username: The GitHub username to search for.

    Returns:
        A dictionary containing repos, stars, commit frequency, and top languages.
    """
    username = username.strip()
    
    # Mock data based on username length to generate varying but stable mock stats
    stars = len(username) * 7 + 12
    repos = len(username) * 3 + 4
    
    return {
        "status": "success",
        "username": username,
        "public_repos": repos,
        "total_stars": stars,
        "top_languages": ["Python", "TypeScript", "HTML/CSS"],
        "recent_commits_count": 142,
        "profile_summary": f"Active developer specializing in Python and frontend. Contributed to {repos} projects with {stars} total stars."
    }

@mcp.tool()
def fetch_coding_profile(platform: str, username: str) -> dict:
    """Retrieves programming performance metrics for a user on competitive coding platforms.

    Args:
        platform: The coding platform name (e.g. 'LeetCode', 'HackerRank', 'CodeChef').
        username: The handle/username of the candidate on that platform.

    Returns:
        A dictionary containing global rank, total solved, and difficulty breakdown.
    """
    platform = platform.lower().strip()
    username = username.strip()
    
    if "leetcode" in platform:
        solved = 245
        rank = 87402
        details = {"easy": 100, "medium": 120, "hard": 25}
    elif "hackerrank" in platform:
        solved = 180
        rank = 12050
        details = {"gold_badges": ["Problem Solving", "Python"], "stars": 5}
    else:
        solved = 95
        rank = 45201
        details = {"rating": 1650, "stars": 3}
        
    return {
        "status": "success",
        "platform": platform,
        "username": username,
        "problems_solved": solved,
        "global_rank": rank,
        "details": details
    }

@mcp.tool()
def search_learning_resources(skills: list[str] | str) -> dict:
    """Looks up learning resources, courses, tutorials, and books for a list of technologies or skills.

    Args:
        skills: A list of technologies or skills to find resources for, or a single skill string.

    Returns:
        A dictionary containing matched books, tutorials, and courses for each skill.
    """
    print(f"[MCP TOOL] search_learning_resources called with skills: {skills}", file=sys.stderr)
    
    if isinstance(skills, str):
        skills = [skills]
        
    resources = {}
    for skill in skills:
        if not isinstance(skill, str):
            continue
        skill_clean = skill.strip().lower()
        if "python" in skill_clean:
            resources[skill] = [
                {"type": "Book", "title": "Fluent Python by Luciano Ramalho", "link": "https://www.oreilly.com/library/view/fluent-python-2nd/9781492056348/"},
                {"type": "Course", "title": "Complete Python BootCamp (Udemy)", "link": "https://www.udemy.com/course/complete-python-bootcamp/"}
            ]
        elif "react" in skill_clean or "typescript" in skill_clean:
            resources[skill] = [
                {"type": "Tutorial", "title": "React Official Documentation", "link": "https://react.dev"},
                {"type": "Course", "title": "Understanding TypeScript (Udemy)", "link": "https://www.udemy.com/course/understanding-typescript/"}
            ]
        elif "docker" in skill_clean or "kubernetes" in skill_clean or "devops" in skill_clean:
            resources[skill] = [
                {"type": "Tutorial", "title": "Docker Labs", "link": "https://labs.play-with-docker.com/"},
                {"type": "Course", "title": "Kubernetes for Developers (Pluralsight)", "link": "https://www.pluralsight.com/"}
            ]
        else:
            resources[skill] = [
                {"type": "Tutorial", "title": f"Intro to {skill} on YouTube", "link": f"https://www.youtube.com/results?search_query=intro+to+{skill.replace(' ', '+')}"},
                {"type": "Course", "title": f"Learn {skill} on Coursera", "link": "https://www.coursera.org/"}
            ]
            
    return {
        "status": "success",
        "resources": resources
    }

if __name__ == "__main__":
    mcp.run()
