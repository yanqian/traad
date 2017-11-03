import os

import rope.base.project
import rope.contrib.codeassist
import rope.refactor.inline
import rope.refactor.rename
from rope.base.change import ChangeToData, DataToChange

from .change_signature import ChangeSignatureMixin
from .extract import ExtractMixin
from .history import HistoryMixin
from .imports import ImportsMixin


def get_all_resources(proj):
    '''Generate a sequence of (path, is_folder) tuples for all
    resources in a project.

    Args:
      proj: The rope Project to scan.

    Returns: An iterable over all resources in a Project, with a tuple
      (path, is_folder) for each.
    '''
    todo = ['']
    while todo:
        res_path = todo[0]
        todo = todo[1:]
        res = proj.get_resource(res_path)
        yield(res.path, res.is_folder())

        if res.is_folder():
            todo.extend((child.path for child in res.get_children()))


# class Change:
#     """This represents a single, fully-specified change that can be
#     performed.

#     This includes both the refactoring type as well as the arguments
#     to the refactoring, the resources, etc. You can direcly call
#     perform() on this object to run the refactoring.
#     """
#     def __init__(self, refactoring, *args):
#         self.refactoring = refactoring
#         self.args = args

#         self.changes = self.refactoring.get_all_changes(*args)
#         self._performed = False

#     @property
#     def descriptions(self):
#         """An iterable of descriptions of the changes that this
#         refactoring will make.
#         """
#         for proj, cset in self.changes:
#             yield cset.get_description()

#     @property
#     def resources(self):
#         """An iterable of resources that this refactoring will modify.
#         """
#         for proj, cset in self.changes:
#             for res in cset.get_changed_resources():
#                 yield res

#     def perform(self):
#         "Perform the refactoring."
#         assert not self._performed

#         multiproject.perform(self.changes)
#         self._performed = True


# class MultiProjectRefactoring:
#     """Support class for performing multi-project refactorings.
#     """
#     def __init__(self, project, refactoring_type, *args):
#         cross_ref = multiproject.MultiProjectRefactoring(
#             refactoring_type,
#             list(project.cross_projects.values()))
#         self.rope_ref = cross_ref(project.proj, *args)

#     def get_change(self, *args):
#         return Change(self.rope_ref, *args)


class Workspace(ChangeSignatureMixin,
                ExtractMixin,
                HistoryMixin,
                ImportsMixin):
    """An actor that controls access to an underlying Rope project.
    """
    def __init__(self,
                 root_project_dir,
                 cross_project_dirs=[]):
        super(Workspace, self).__init__()

        self._root_project = rope.base.project.Project(root_project_dir)

        self._cross_projects = dict()

        cross_dirs = set(cross_project_dirs)
        cross_dirs.discard(root_project_dir)
        for cross_dir in cross_dirs:
            self.add_cross_project(cross_dir)

    def close(self):
        self.root_project.close()

    def add_cross_project(self, directory):
        """Add a cross project rooted at `directory`."""
        self._cross_projects[directory] = rope.base.project.Project(directory)

    def remove_cross_project(self, directory):
        """Remove the cross project rooted at `directory`."""
        del self._cross_projects[directory]

    @property
    def root_project(self):
        return self._root_project

    @property
    def cross_projects(self):
        return self._cross_projects.values()

    @property
    def projects(self):
        yield self.root_project
        for cp in self.cross_projects:
            yield cp

    def to_relative_path(self, path, project=None):
        '''Get a version of a path relative to the project root.

        If ``path`` is already relative, then it is unchanged. If
        ``path`` is absolute, then it is made relative to the project
        root.

        Args:
          path: The path to make relative.
          project: The project to use as the root directory [default: root project]

        Returns: ``path`` relative to the project root.

        '''
        project = project or self.root_project

        if os.path.isabs(path):
            path = os.path.relpath(
                os.path.realpath(path),
                project.root.real_path)
        return path

    def get_resource(self, path):
        return self.root_project.get_resource(
            self.to_relative_path(path))

    def get_changes(self,
                    refactoring_type,
                    path,
                    refactoring_args,
                    change_args):
        """Calculate the changes for a specific refactoring.

        Args:
          refactoring_type: The class of the refactoring to perform (e.g.
            `rope.refactor.rename.Rename`)
          path: The path to the resource in the project.
          refactoring_args: The sequence of args to pass to the
            `refactoring_type` constructor.
          change_args: The sequence of args to pass to
            `MultiProjectRefactoring.get_all_changes`.

        Returns: All changes that would be performed by the refactoring. A list
          of the form `[[<project>, [<change set>]]`.
        """
        ref = refactoring_type(
            self.root_project,
            self.get_resource(
                self.to_relative_path(
                    path)),
            *refactoring_args)
        return ref.get_changes(*change_args)

    def perform(self, changes):
        self.root_project.do(changes)

    def rename(self, path, offset, name):
        ref = rope.refactor.rename.Rename(
            self.root_project,
            self.get_resource(path),
            offset)
        return ref.get_changes(name)

    def inline(self, path, offset):
        ref = rope.refactor.inline.create_inline(
            self.root_project,
            self.get_resource(path),
            offset)
        return ref.get_changes()

    def code_assist(self, code, offset, path):
        '''Get code-assist completions for a point in a file.

        ``path`` may be absolute or relative. If ``path`` is relative,
        then it must to be relative to the root of the project.

        Args:
          code: The source code in which the completion should
            happen. Note that this may differ from the contents of the
            resource at ``path``.
          offset: The offset into ``code`` where the completion should
            happen.
          path: The path to the resource in which the completion is
            being done.

        Returns: A list of tuples of the form (name, documentation,
          scope, type) for each possible completion.
        '''

        results = rope.contrib.codeassist.code_assist(
            self.root_project,
            code,
            offset,
            self.get_resource(path))
        rslt = [(r.name, r.get_doc(), r.scope, r.type) for r in results]
        return rslt

    def get_doc(self, code, offset, path):
        '''Get docstring for an object.

        ``path`` may be absolute or relative. If ``path`` is relative,
        then it must to be relative to the root of the project.

        Args:
          code: The source code.
          offset: An offset into ``code`` of the object to query.
          path: The path to the resource in which the completion is
            being done.

        Returns: The docstring for the object, or None if there is no such
            documentation.
        '''

        return rope.contrib.codeassist.get_doc(
            self.root_project,
            code,
            offset,
            self.get_resource(path))

    def get_calltip(self, code, offset, path):
        """Get the calltip of a function.

        ``path`` may be absolute or relative. If ``path`` is relative,
        then it must be relative to the root of the project.

        Args:
          code: The source code.
          offset: An offset into ``code`` of the object to query.
          path: The path to the resource in which the search is
            being done.

        Returns: A calltip string.
        """

        return rope.contrib.codeassist.get_calltip(
            self.root_project,
            code,
            offset,
            self.get_resource(path))


    def __repr__(self):
        return 'Project("{}")'.format(
            self.root_project.root.real_path)

    def __str__(self):
        return repr(self)

    def _root_to_project(self, root):
        if root == self.root_project.root.real_path:
            return self.root_project
        return self.cross_projects[root]


def changes_to_data(changes):
    return ChangeToData()(changes)


def data_to_changes(workspace, data):
    return DataToChange(workspace.root_project)(data)
