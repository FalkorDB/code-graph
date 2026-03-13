import os
import unittest
from git import Repo
from api import (
    Graph,
    Project,
    switch_commit
)

repo      = None  # repository
graph     = None  # code graph
git_graph = None  # git graph

class Test_Git_History(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This runs once before all tests in this class

        global repo
        global graph
        global git_graph

        # Get the current file path
        current_file_path = os.path.abspath(__file__)

        # Get the directory of the current file
        current_dir = os.path.dirname(current_file_path)

        # Append 'git_repo' to the current directory
        repo_dir = os.path.join(current_dir, 'git_repo')

        # Checkout HEAD commit
        repo = Repo(repo_dir)
        repo.git.checkout("HEAD")

        proj      = Project.from_local_repository(repo_dir)
        graph     = proj.analyze_sources()
        git_graph = proj.process_git_history()

    def assert_file_not_exists(self, path: str, name: str, ext: str) -> None:
        f = graph.get_file(path, name, ext)
        self.assertIsNone(f)

    def assert_file_exists(self, path: str, name: str, ext: str) -> None:
        f = graph.get_file(path, name, ext)

        self.assertIsNotNone(f)
        self.assertEqual(f.ext, ext)
        self.assertEqual(f.path, path)
        self.assertEqual(f.name, name)

    def test_git_graph_structure(self):
        # validate git graph structure
        c = repo.commit("HEAD")

        while True:
            commits = git_graph.get_commits([c.short_id])

            self.assertEqual(len(commits), 1)
            actual = commits[0]

            self.assertEqual(c.short_id,       actual['hash'])
            self.assertEqual(c.message,        actual['message'])
            self.assertEqual(c.author.name,    actual['author'])
            self.assertEqual(c.committed_date, actual['date'])

            # Advance to previous commit
            if len(c.parents) == 0:
                break

            c = c.parents[0]

    def test_git_transitions(self):
        # our test git repo:
        #
        # commit df8d021dbae077a39693c1e76e8438006d62603e (HEAD, main)
        # removed b.py

        # commit 5ec6b14612547393e257098e214ae7748ed12c50
        # added both b.py and c.py

        # commit c4332d05bc1b92a33012f2ff380b807d3fbb9c2e
        # modified a.py

        # commit fac1698da4ee14c215316859e68841ae0b0275b0
        # created a.py
        
        #----------------------------------------------------------------------
        # Going backwards
        #----------------------------------------------------------------------

        # HEAD commit
        switch_commit('git_repo', 'df8d021dbae077a39693c1e76e8438006d62603e')

        # a.py and c.py should exists
        self.assert_file_exists("", "a.py", ".py")
        self.assert_file_exists("", "c.py", ".py")

        # b.py should NOT exists
        self.assert_file_not_exists("", "b.py", ".py")

        #-----------------------------------------------------------------------
        # df8d02 -> 5ec6b1
        #-----------------------------------------------------------------------

        switch_commit('git_repo', '5ec6b14612547393e257098e214ae7748ed12c50')

        # a.py, b.py and c.py should exists
        self.assert_file_exists("", "a.py", ".py")
        self.assert_file_exists("", "b.py", ".py")
        self.assert_file_exists("", "c.py", ".py")

        #-----------------------------------------------------------------------
        # 5ec6b1 -> c4332d
        #-----------------------------------------------------------------------

        switch_commit('git_repo', 'c4332d05bc1b92a33012f2ff380b807d3fbb9c2e')

        # only a.py, should exists
        self.assert_file_exists("", "a.py", ".py")

        # b.py and c.py shouldn't exists
        self.assert_file_not_exists("", "b.py", ".py")
        self.assert_file_not_exists("", "c.py", ".py")

        #-----------------------------------------------------------------------
        # c4332d -> fac169
        #-----------------------------------------------------------------------

        switch_commit('git_repo', 'fac1698da4ee14c215316859e68841ae0b0275b0')

        # only a.py, should exists
        self.assert_file_exists("", "a.py", ".py")

        # b.py and c.py shouldn't exists
        self.assert_file_not_exists("", "b.py", ".py")
        self.assert_file_not_exists("", "c.py", ".py")

        #----------------------------------------------------------------------
        # Going forward
        #----------------------------------------------------------------------

        #-----------------------------------------------------------------------
        # fac169 -> c4332d0
        #-----------------------------------------------------------------------

        switch_commit('git_repo', 'c4332d05bc1b92a33012f2ff380b807d3fbb9c2e')

        # only a.py, should exists
        self.assert_file_exists("", "a.py", ".py")

        # b.py and c.py shouldn't exists
        self.assert_file_not_exists("", "b.py", ".py")
        self.assert_file_not_exists("", "c.py", ".py")

        #-----------------------------------------------------------------------
        # c4332d0 -> 5ec6b14
        #-----------------------------------------------------------------------

        #import ipdb; ipdb.set_trace()
        switch_commit('git_repo', '5ec6b14612547393e257098e214ae7748ed12c50')

        # a.py, b.py and c.py should exists
        self.assert_file_exists("", "a.py", ".py")
        self.assert_file_exists("", "b.py", ".py")
        self.assert_file_exists("", "c.py", ".py")

        #-----------------------------------------------------------------------
        # 5ec6b14 -> HEAD
        #-----------------------------------------------------------------------

        switch_commit('git_repo', 'df8d021dbae077a39693c1e76e8438006d62603e')

        # a.py and c.py should exists
        self.assert_file_exists("", "a.py", ".py")
        self.assert_file_exists("", "c.py", ".py")

        # b.py should NOT exists
        self.assert_file_not_exists("", "b.py", ".py")


    def test_git_multi_commit_transition(self):
        # our test git repo:
        #
        # commit df8d021dbae077a39693c1e76e8438006d62603e (HEAD, main)
        # removed b.py

        # commit 5ec6b14612547393e257098e214ae7748ed12c50
        # added both b.py and c.py

        # commit c4332d05bc1b92a33012f2ff380b807d3fbb9c2e
        # modified a.py

        # commit fac1698da4ee14c215316859e68841ae0b0275b0
        # created a.py

        # Start at the HEAD commit
        switch_commit('git_repo', 'df8d021dbae077a39693c1e76e8438006d62603e')

        # a.py and c.py should exists
        self.assert_file_exists("", "a.py", ".py")
        self.assert_file_exists("", "c.py", ".py")

        # b.py should NOT exists
        self.assert_file_not_exists("", "b.py", ".py")

        # Switch over to the very first commit fac1698da4ee14c215316859e68841ae0b0275b0

        switch_commit('git_repo', 'fac1698da4ee14c215316859e68841ae0b0275b0')

        # a.py
        self.assert_file_exists("", "a.py", ".py")

        # b.py and c.py should NOT exists
        self.assert_file_not_exists("", "b.py", ".py")
        self.assert_file_not_exists("", "c.py", ".py")

        # Switch back to HEAD
        switch_commit('git_repo', 'df8d021dbae077a39693c1e76e8438006d62603e')

        # a.py and c.py should exists
        self.assert_file_exists("", "a.py", ".py")
        self.assert_file_exists("", "c.py", ".py")

        # b.py should NOT exists
        self.assert_file_not_exists("", "b.py", ".py")
