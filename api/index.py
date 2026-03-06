""" Main API module for CodeGraph. """
import os
from pathlib import Path
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from api.analyzers.source_analyzer import SourceAnalyzer
from api.git_utils import git_utils
from api.git_utils.git_graph import GitGraph
from api.graph import Graph, get_repos, graph_exists
from api.info import get_repo_info
from api.llm import ask
from api.project import Project
from .auto_complete import prefix_search

# Load environment variables from .env file
load_dotenv()

# Configure the logger
import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SECRET_TOKEN = os.getenv('SECRET_TOKEN')
def verify_token(token):
    """ Verify the token provided in the request """
    return token == SECRET_TOKEN or (token is None and SECRET_TOKEN is None)

def token_required(f):
    """ Decorator to protect routes with token authentication """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')  # Get token from header
        if not verify_token(token):
            return jsonify(message="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)

def public_access(f):
    """ Decorator to protect routes with public access """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        public = os.environ.get("CODE_GRAPH_PUBLIC", "0")  # Get public access setting
        if public != "1":
            return jsonify(message="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/graph_entities', methods=['GET'])
@token_required  # Apply token authentication decorator
def graph_entities():
    """
    Endpoint to fetch sub-graph entities from a given repository.
    The repository is specified via the 'repo' query parameter.

    Returns:
        - 200: Successfully returns the sub-graph.
        - 400: Missing or invalid 'repo' parameter.
        - 500: Internal server error or database connection issue.
    """

    # Access the 'repo' parameter from the GET request
    repo = request.args.get('repo')

    if not repo:
        logging.error("Missing 'repo' parameter in request.")
        return jsonify({"status": "Missing 'repo' parameter"}), 400

    if not graph_exists(repo):
        logging.error("Missing project %s", repo)
        return jsonify({"status": f"Missing project {repo}"}), 400

    try:
        # Initialize the graph with the provided repo and credentials
        g = Graph(repo)

        # Retrieve a sub-graph of up to 500 entities
        sub_graph = g.get_sub_graph(500)

        logging.info("Successfully retrieved sub-graph for repo: %s", repo)
        response = {
            'status': 'success',
            'entities': sub_graph
        }

        return jsonify(response), 200

    except Exception as e:
        logging.error("Error retrieving sub-graph for repo '%s': %s", repo, e)
        return jsonify({"status": "Internal server error"}), 500


@app.route('/get_neighbors', methods=['POST'])
@token_required  # Apply token authentication decorator
def get_neighbors():
    """
    Endpoint to get neighbors of a nodes list in the graph.
    Expects 'repo' and 'node_ids' as body parameters.

    Returns:
        JSON response containing neighbors or error messages.
    """

    # Get JSON data from the request
    data = request.get_json()

    # Get query parameters
    repo    = data.get('repo')
    node_ids = data.get('node_ids')

    # Validate 'repo' parameter
    if not repo:
        logging.error("Repository name is missing in the request.")
        return jsonify({"status": "Repository name is required."}), 400

    # Validate 'node_ids' parameter
    if not node_ids:
        logging.error("Node IDs is missing in the request.")
        return jsonify({"status": "Node IDs is required."}), 400

    # Validate repo exists
    if not graph_exists(repo):
        logging.error("Missing project %s", repo)
        return jsonify({"status": f"Missing project {repo}"}), 400

    # Initialize the graph with the provided repository
    g = Graph(repo)

    # Fetch the neighbors of the specified node
    neighbors = g.get_neighbors(node_ids)

    # Log and return the neighbors
    logging.info("Successfully retrieved neighbors for node IDs %s in repo '%s'.", node_ids, repo)

    response = {
        'status': 'success',
        'neighbors': neighbors
    }

    return jsonify(response), 200

@app.route('/auto_complete', methods=['POST'])
@token_required  # Apply token authentication decorator
def auto_complete():
    """
    Endpoint to process auto-completion requests for a repository based on a prefix.

    Returns:
        JSON response with auto-completion suggestions or an error message.
    """

    # Get JSON data from the request
    data = request.get_json()

    # Validate that 'repo' is provided
    repo = data.get('repo')
    if repo is None:
        return jsonify({'status': 'Missing mandatory parameter "repo"'}), 400

    # Validate that 'prefix' is provided
    prefix = data.get('prefix')
    if prefix is None:
        return jsonify({'status': 'Missing mandatory parameter "prefix"'}), 400

    # Validate repo exists
    if not graph_exists(repo):
        return jsonify({'status': f'Missing project {repo}'}), 400

    # Fetch auto-completion results
    completions = prefix_search(repo, prefix)

    # Create a success response
    response = {
        'status': 'success',
        'completions': completions
    }

    return jsonify(response), 200

@app.route('/list_repos', methods=['GET'])
@token_required  # Apply token authentication decorator
def list_repos():
    """
    Endpoint to list all available repositories.

    Returns:
        JSON response with a list of repositories or an error message.
    """

    # Fetch list of repositories
    repos = get_repos()

    # Create a success response with the list of repositories
    response = {
        'status': 'success',
        'repositories': repos
    }

    return jsonify(response), 200

@app.route('/repo_info', methods=['POST'])
@token_required  # Apply token authentication decorator
def repo_info():
    """
    Endpoint to retrieve information about a specific repository.

    Expected JSON payload:
        {
            "repo": <repository name>
        }

    Returns:
        JSON: A response containing the status and graph statistics (node and edge counts).
            - 'status': 'success' if successful, or an error message.
            - 'info': A dictionary with the node and edge counts if the request is successful.
    """

    # Get JSON data from the request
    data = request.get_json()

    # Validate the 'repo' parameter
    repo = data.get('repo')
    if repo is None:
        return jsonify({'status': 'Missing mandatory parameter "repo"'}), 400

    # Initialize the graph with the provided repository name
    g = Graph(repo)

    # Retrieve statistics from the graph
    stats = g.stats()
    info = get_repo_info(repo)

    if stats is None or info is None:
        return jsonify({'status': f'Missing repository "{repo}"'}), 400

    stats |= info

    # Create a response
    response = {
        'status': 'success',
        'info': stats
    }

    return jsonify(response), 200

@app.route('/find_paths', methods=['POST'])
@token_required  # Apply token authentication decorator
def find_paths():
    """
    Finds all paths between a source node (src) and a destination node (dest) in the graph.
    The graph is associated with the repository (repo) provided in the request.

    Request Body (JSON):
        - repo (str): Name of the repository.
        - src (int): ID of the source node.
        - dest (int): ID of the destination node.

    Returns:
        A JSON response with:
        - status (str): Status of the request ("success" or "error").
        - paths (list): List of paths between the source and destination nodes.
    """

    # Get JSON data from the request
    data = request.get_json()

    # Validate 'repo' parameter
    repo = data.get('repo')
    if repo is None:
        return jsonify({'status': 'Missing mandatory parameter "repo"'}), 400

    # Validate 'src' parameter
    src = data.get('src')
    if src is None:
        return jsonify({'status': 'Missing mandatory parameter "src"'}), 400
    if not isinstance(src, int):
        return jsonify({'status': "src node id must be int"}), 400

    # Validate 'dest' parameter
    dest = data.get('dest')
    if dest is None:
        return jsonify({'status': 'Missing mandatory parameter "dest"'}), 400
    if not isinstance(dest, int):
        return jsonify({'status': "dest node id must be int"}), 400

    if not graph_exists(repo):
        logging.error("Missing project %s", repo)
        return jsonify({"status": f"Missing project {repo}"}), 400

    # Initialize graph with provided repo and credentials
    g = Graph(repo)

    # Find paths between the source and destination nodes
    paths = g.find_paths(src, dest)

    # Create and return a successful response
    response = { 'status': 'success', 'paths': paths }

    return jsonify(response), 200

@app.route('/chat', methods=['POST'])
@token_required  # Apply token authentication decorator
def chat():
    """ Endpoint to chat with the CodeGraph language model. """

    # Get JSON data from the request
    data = request.get_json()

    # Validate 'repo' parameter
    repo = data.get('repo')
    if repo is None:
        return jsonify({'status': 'Missing mandatory parameter "repo"'}), 400

    # Get optional 'label' and 'relation' parameters
    msg = data.get('msg')
    if msg is None:
        return jsonify({'status': 'Missing mandatory parameter "msg"'}), 400

    answer = ask(repo, msg)

    # Create and return a successful response
    response = { 'status': 'success', 'response': answer }

    return jsonify(response), 200

@app.route('/analyze_folder', methods=['POST'])
@token_required  # Apply token authentication decorator
def analyze_folder():
    """
    Endpoint to analyze local source code
    Expects 'path' and optionally an ignore list.

    Returns:
        JSON response with status and error message if applicable
        Status codes:
            200: Success
            400: Invalid input
            500: Internal server error
    """

    # Get JSON data from the request
    data = request.get_json()

    # Get query parameters
    path      = data.get('path')
    ignore    = data.get('ignore', [])

    # Validate input parameters
    if not path:
        logging.error("'path' is missing from the request.")
        return jsonify({"status": "'path' is required."}), 400

    # Validate path exists and is a directory
    if not os.path.isdir(path):
        logging.error("Path '%s' does not exist or is not a directory", path)
        return jsonify({"status": "Invalid path: must be an existing directory"}), 400

    # Validate ignore list contains valid paths
    if not isinstance(ignore, list):
        logging.error("'ignore' must be a list of paths")
        return jsonify({"status": "'ignore' must be a list of paths"}), 400

    proj_name = Path(path).name

    # Initialize the graph with the provided project name
    g = Graph(proj_name)

    # Analyze source code within given folder
    analyzer = SourceAnalyzer()
    analyzer.analyze_local_folder(path, g, ignore)

    # Return response
    response = {
            'status': 'success',
            'project': proj_name
        }
    return jsonify(response), 200

@app.route('/analyze_repo', methods=['POST'])
@public_access  # Apply public access decorator
@token_required  # Apply token authentication decorator
def analyze_repo():
    """
    Analyze a GitHub repository.

    Expected JSON payload:
    {
        "repo_url": "string",
        "ignore": ["string"]  # optional
    }

    Returns:
        JSON response with processing status
    """

    data = request.get_json()
    url = data.get('repo_url')
    if url is None:
        return jsonify({'status': 'Missing mandatory parameter "url"'}), 400
    logger.debug('Received repo_url: %s', url)

    ignore = data.get('ignore', [])

    proj = Project.from_git_repository(url)
    proj.analyze_sources(ignore)
    proj.process_git_history(ignore)

    # Create a response
    response = {
        'status': 'success',
    }

    return jsonify(response), 200

@app.route('/switch_commit', methods=['POST'])
@public_access  # Apply public access decorator
@token_required  # Apply token authentication decorator
def switch_commit():
    """
    Endpoint to switch a repository to a specific commit.

    Returns:
        JSON response with the change set or an error message.
    """

    # Get JSON data from the request
    data = request.get_json()

    # Validate that 'repo' is provided
    repo = data.get('repo')
    if repo is None:
        return jsonify({'status': 'Missing mandatory parameter "repo"'}), 400

    # Validate that 'commit' is provided
    commit = data.get('commit')
    if commit is None:
        return jsonify({'status': 'Missing mandatory parameter "commit"'}), 400

    # Attempt to switch the repository to the specified commit
    git_utils.switch_commit(repo, commit)

    # Create a success response
    response = {
        'status': 'success'
    }

    return jsonify(response), 200

@app.route('/list_commits', methods=['POST'])
@public_access  # Apply public access decorator
@token_required  # Apply token authentication decorator
def list_commits():
    """
    Endpoint to list all commits of a specified repository.

    Request JSON Structure:
    {
        "repo": "repository_name"
    }

    Returns:
        JSON response with a list of commits or an error message.
    """

    # Get JSON data from the request
    data = request.get_json()

    # Validate the presence of the 'repo' parameter
    repo = data.get('repo')
    if repo is None:
        return jsonify({'status': f'Missing mandatory parameter "repo"'}), 400

    # Initialize GitGraph object to interact with the repository
    git_graph = GitGraph(git_utils.GitRepoName(repo))

    # Fetch commits from the repository
    commits = git_graph.list_commits()

    # Return success response with the list of commits
    response = {
        'status': 'success',
        'commits': commits
    }

    return jsonify(response), 200