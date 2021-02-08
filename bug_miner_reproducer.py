import csv
import json
import git
import time
import os
from subprocess import Popen
from dir_structure import DirStructure, DirId
import sys
from reproducer import Reproducer
from subprocess import Popen
import tempfile
from ast import literal_eval
import pandas as pd
import codecs


class BugMinerReproducer(Reproducer):
    BUG_MINER_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), r"bug_miner"))
    RESULTS_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), r"results"))

    def __init__(self, id, failing_tests, dir_id, repo_url, diffs, blamed_components, fix):
        super(BugMinerReproducer, self).__init__(id, map(lambda t: t.replace("#", "."), failing_tests), dir_id)
        self.repo_path = repo_url
        self.parent = id
        self.diffs = list(filter(literal_eval, map(lambda x: x.encode('utf-8'), diffs)))
        self.blamed_components = reduce(list.__add__, map(lambda x: x.split("@"), blamed_components), [])
        self.fix_commit = fix

    def get_repo(self):
        return self.repo_path

    def clone(self):
        Popen(['git', 'clone', self.get_repo(), self.get_dir_id().clones]).wait()
        Popen(['git', '-C', self.get_dir_id().clones, "checkout", self.parent]).wait()

    def apply_patch(self):
        for diff in self.diffs:
            if literal_eval(diff):
                f, path_to_diff = tempfile.mkstemp()
                os.close(f)
                with codecs.open(path_to_diff, "w", "utf-8") as f:
                    f.write(literal_eval(diff) + "\n")
                    f.flush()
                repo = git.Repo(self.dir_id.clones)
                repo.git.apply("--whitespace=nowarn", path_to_diff)
                os.remove(path_to_diff)

    def fix(self):
        # Popen(['git', '-C', self.get_dir_id().clones, "checkout", self.fix_commit]).wait()
        pass

    def extract_buggy_functions(self):
        return self.blamed_components

    def get_non_pass_outcomes(self):
        return ['failure']

    # def clear(self):
    #     git.Repo(self.get_dir_id().clones).git.checkout('--', '.')

    @staticmethod
    def read_bug_miner_csv(project_name, git_url):
        csv_path = os.path.join(BugMinerReproducer.BUG_MINER_DIR, project_name + ".csv")
        df = pd.read_csv(csv_path)
        ans = dict()
        commits = dict()
        map(lambda x: commits.setdefault(x['parent'], []).append(x), map(lambda y: y[1].to_dict(), df.iterrows()))
        for bug_data in commits:
            ans[bug_data] = BugMinerReproducer(bug_data, list(set(map(lambda x: x['testcase'], commits[bug_data]))),
                                               DirId(DirStructure(BugMinerReproducer.RESULTS_DIR), bug_data),
                                               git_url,
                                               list(set(map(lambda x: x['diff'], commits[bug_data]))),
                                               list(set(map(lambda x: x['blamed_components'], commits[bug_data]))),
                                               list(set(map(lambda x: x['commit'], commits[bug_data]))))
        return ans


def clone_repo(base, url):
    git.Repo.clone_from(url, base)


if __name__ == "__main__":
    import settings
    git_url, jira_url = settings.projects.get(sys.argv[1])
    projects = BugMinerReproducer.read_bug_miner_csv(sys.argv[1], git_url)
    keys = sorted(list(projects.keys()))
    if len(sys.argv) > 2 and int(sys.argv[2]) < len(keys):
        projects[keys[int(sys.argv[2])]].dump()
    # else:
    #     for p in projects:
    #         projects[p].dump()
