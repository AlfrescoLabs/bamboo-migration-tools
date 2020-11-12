import re
import yaml

from datetime import datetime
from functools import reduce
from github import Github, UnknownObjectException, InputGitAuthor


def _git_url_to_github_path(git_url):
    if git_url.startswith('git@github.com:'):
        return git_url[len('git@github.com:'):].split('.git')[0]
    elif git_url.startswith('https://github.com/'):
        return git_url[len('https://github.com/'):].split('.git')[0]
    else:
        return None


class LinkedRepositoriesList():

    def __init__(self, file_path):
        self.file_path = file_path

    def __getitem__(self, name):
        if not hasattr(self, 'repositories'):
            self.__read_linked_repositories()
        return self.repositories[name]

    def get(self, name, default_value=None):
        if not hasattr(self, 'repositories'):
            self.__read_linked_repositories()
        return self.repositories.get(name, default_value)

    def __read_linked_repositories(self):
        try:
            with open(self.file_path, newline='') as csv_file:
                csv_reader = csv.reader(csv_file)
                self.repositories = dict([ csv_row for csv_row in csv_reader if len(csv_row) == 2 ])
        except FileNotFoundError:
            self.repositories = {}


class BambooProperties(yaml.YAMLObject):
     yaml_loader = yaml.SafeLoader


class Applicability(yaml.YAMLObject):
    yaml_loader = yaml.SafeLoader
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.api.builders.Applicability'
    def __init__(self, notification_type):
        self.notification_type = notification_type
    @classmethod
    def from_yaml(cls, loader, node):
        return Applicability(node.value)
    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.notification_type)


class TimeDuration(yaml.YAMLObject):
    yaml_loader = yaml.SafeLoader
    yaml_tag = 'tag:yaml.org,2002:java.time.Duration'
    def __init__(self, duration):
        self.duration = duration
    @classmethod
    def from_yaml(cls, loader, node):
        return TimeDuration(node.value)
    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.duration)


class PlanProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.plan.PlanProperties'
    def __init__(self, description, enabled, key, name, oid, project, repositories, stages, triggers, variables):
        self.description = description
        self.enabled = enabled
        self.key = key
        self.name = name
        self.oid = oid
        self.project = project
        self.repositories = repositories
        self.stages = stages
        self.triggers = triggers
        self.variables = variables
    def get_default_repository_definition(self):
        if len(self.repositories) > 0:
            return self.repositories[0]['repositoryDefinition']
        else:
            return None
    def get_repository_definition(self):
        for repo in self.repositories:
            yield repo['repositoryDefinition']
    def __repr__(self):
        return "%s(project=%r, key=%r, name=%r)" % (
            self.__class__.__name__, self.project['key']['key'], self.key['key'], self.name)


class AnyVcsRepositoryProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.repository.AnyVcsRepositoryProperties'
    def __init__(self, description, name, oid, atlassianPlugin, branchConfiguration, serverConfiguration):
        self.description = description
        self.name = name
        self.oid = oid
        self.atlassianPlugin = atlassianPlugin
        self.branchConfiguration = branchConfiguration
        self.serverConfiguration = serverConfiguration
    def __repr__(self):
        return "%s(name=%r, description=%r)" % (
            self.__class__.__name__, self.name, self.description)
    def git_url(self, context=None):
        return 'git@github.com:%s.git' % (self.github_path(context))
    def github_path(self, context=None):
        try:
            return self.serverConfiguration['repository.github.repository']
        except KeyError:
            return None


class GitRepositoryProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.repository.git.GitRepositoryProperties'
    def __init__(self, description, name, oid, url, branch):
        self.description = description
        self.name = name
        self.oid = oid
        self.url = url
        self.branch = branch
    def __repr__(self):
        return "%s(oid=%r, url=%r, branch=%r)" % (
            self.__class__.__name__, self.oid, self.url, self.branch)
    def git_url(self, context=None):
        return self.url
    def github_path(self, context=None):
        return _git_url_to_github_path(self.url)


class SharedCredentialsAuthenticationProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.repository.git.SharedCredentialsAuthenticationProperties'


class LinkedGlobalRepository(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.repository.PlanRepositoryLinkProperties$LinkedGlobalRepository'
    def __init__(self, description, name, oid, parent, repositoryViewerProperties, atlassianPlugin, branch, url):
        self.description = description
        self.name = name
        self.oid = oid
        self.parent = parent
        self.repositoryViewerProperties = repositoryViewerProperties
        self.atlassianPlugin = atlassianPlugin
        self.branch = branch
        self.url = url
    def __repr__(self):
        return "%s(parent=%r)" % (self.__class__.__name__, self.parent)
    def git_url(self, context=None):
        context = context or {}
        if hasattr(self, 'url') and self.url is not None:
            git_url = self.url
        elif self.parent is not None:
            linked_repositories = context.get('linked_repositories')
            if linked_repositories:
                git_url = linked_repositories.get(self.parent) or self.parent
            else:
                git_url = self.parent
        return git_url
    def github_path(self, context=None):
        git_url = self.git_url(context)
        return _git_url_to_github_path(git_url)


class PlanSpec(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.util.BambooSpecProperties'
    def __init__(self, rootEntity):
        self.rootEntity = rootEntity
    def __repr__(self):
        return 'rootEntity'


class ConcurrentBuildsProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.plan.configuration.ConcurrentBuildsProperties'


class UnsupportedTaskConfiguration(Exception):
    pass


class BambooTaskProperties(BambooProperties):
    variable_mappings = dict((
        ('buildNumber', 'TRAVIS_BUILD_NUMBER'),
        ('planRepository.branchName', 'TRAVIS_BRANCH'),
        ('planRepository.1.branchName', 'TRAVIS_BRANCH'),
    ))
    @classmethod
    def _travis_variable_refs(cls, match):
        var_name = match.group(1)
        if var_name.replace('_', '.') in cls.variable_mappings:
            return '${%s}' % (cls.variable_mappings[var_name.replace('_', '.')])
        else:
            return '${%s}' % (var_name.upper().replace('.', '_'))
    @classmethod
    def _travis_variable_assign(cls, match):
        var_name = match.group(1)
        return '%s' % (var_name.upper().replace('.', '_'))
    @classmethod
    def _convert_variable_names(cls, bamboo_variables):
        return re.sub('\$\{?bamboo[\._]([\._\w]+)\}?', cls._travis_variable_refs, bamboo_variables)
    def _convert_variable_assignments(cls, bamboo_variables):
        return re.sub('bamboo[\._]([\._\w]+)', cls._travis_variable_assign, bamboo_variables)
    def wrap_command(self, cmd, working_directory=None, environment_vars=None):
        env_prefix = environment_vars and ('%s ' % (self._convert_variable_names(environment_vars))) or ''
        cmd_with_prefix = env_prefix + cmd
        if working_directory:
            return 'pushd "%s" && %s && popd' % (working_directory, cmd_with_prefix)
        else:
            return cmd_with_prefix

class VcsCheckoutTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.VcsCheckoutTaskProperties'
    def __init__(self, description, enabled, checkoutItems, cleanCheckout):
        self.description = description
        self.enabled = enabled
        self.checkoutItems = checkoutItems
        self.cleanCheckout = cleanCheckout
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        git_repos = [checkoutItem for checkoutItem in self.checkoutItems if checkoutItem['defaultRepository'] is not True]
        return {'before_script': ['git clone [repo:%s] %s' % (repo['repository']['name'], repo['path'] or '') for repo in git_repos]}

class ArtifactDownloaderTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.ArtifactDownloaderTaskProperties'
    def __init__(self, description, enabled, artifacts, sourcePlan):
        self.description = description
        self.enabled = enabled
        self.artifacts = artifacts
        self.sourcePlan = sourcePlan
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        return {'before_install': [ 'sudo apt-get -y install awscli'] +
                ['AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= AWS_DEFAULT_REGION= aws s3 cp "s3://${ARTIFACTS_BUCKET}/${TRAVIS_REPO_SLUG}/${TRAVIS_BUILD_NUMBER}/${TRAVIS_JOB_NUMBER}/%s" "./%s"' % (artifact['artifactName'], artifact['path']) for artifact in self.artifacts]}

class MavenTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.MavenTaskProperties'
    def __init__(self, description, enabled, environmentVariables, executableLabel, goal, hasTests, jdk, projectFile,
                 testDirectoryOption, testResultsDirectory, useMavenReturnCode, version, workingSubdirectory):
        self.description = description
        self.enabled = enabled
        self.environmentVariables = environmentVariables
        self.executableLabel = executableLabel
        self.goal = goal
        self.hasTests = hasTests
        self.jdk = jdk
        self.projectFile = projectFile
        self.testDirectoryOption = testDirectoryOption
        self.testResultsDirectory = testResultsDirector
        self.useMavenReturnCode = useMavenReturnCode
        self.version = version
        self.workingSubdirectory = workingSubdirectory
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_language(self):
        return ('java', self.jdk)
    def get_jvm(self):
        return 'java'
    def get_jobs(self):
        mvn_options = ''
        if self.projectFile:
            mvn_options += ' -F "%s"' % (self.projectFile)
        mvn_cmd = 'mvn %s%s' % (mvn_options, self._convert_variable_names(self.goal.replace('\n', ' ')))
        return {'script': self.wrap_command(mvn_cmd, self.workingSubdirectory, self.environmentVariables)}

class AntTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.AntTaskProperties'
    def __init__(self, target, buildFile, workingSubdirectory, environmentVariables):
        self.target = target
        self.buildFile = buildFile
        self.workingSubdirectory = workingSubdirectory
        self.environmentVariables = environmentVariables
    def get_language(self):
        return ('java')
    def get_jobs(self):
        ant_options = ''
        if self.buildFile:
            ant_options += ' -f "%s"' % (self.buildFile)
        ant_cmd = 'ant %s%s' % (ant_options, re.sub('\$\{bamboo.([\._\w]+)\}', self._travis_variable_refs, self.goal))
        return {'script': self.wrap_command(ant_cmd, self.workingSubdirectory, self.environmentVariables)}

class ScriptTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.ScriptTaskProperties'
    def __init__(self, description, enabled, argument, body, environmentVariables, interpreter, location, path, workingSubdirectory):
        self.description = description
        self.enabled = enabled
        self.argument = argument
        self.body = body
        self.environmentVariables = environmentVariables
        self.interpreter = interpreter
        self.location = location
        self.path = path
        self.workingSubdirectory = workingSubdirectory
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        if self.location == 'INLINE':
            pushd_cmd = ('pushd "%s" && ' % (self.workingSubdirectory,)) if self.workingSubdirectory else ''
            popd_cmd = '&& popd' if self.workingSubdirectory else ''
            script_body_lines = self.body.strip().splitlines()
            if len(script_body_lines) > 1:
                script_lines = [('%s%s sh -c "$(cat <<\'EOF\'' % (pushd_cmd, self._convert_variable_names(self.environmentVariables or ''))).strip()]
                script_lines += [ self._convert_variable_names(line) for line in script_body_lines]
                script_lines += ['EOF', (')" %s%s' % (self._convert_variable_names('script.sh ' + self.argument if self.argument else ''), popd_cmd)).strip()]
            else:
                script_lines = [pushd_cmd + self.wrap_command(script_body_lines[0], self.workingSubdirectory, self.environmentVariables) + popd_cmd]
        elif self.location == 'FILE':
            script_cmd = ('%s %s' % (self.path, self._convert_variable_names(self.argument or ''))).strip()
            script_lines = [self.wrap_command(script_cmd, self.workingSubdirectory, self.environmentVariables)]
        else:
            raise Exception('Not a valid script location value')
        return {'script': '\n'.join(script_lines)}

class GruntTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.GruntTaskProperties'
    def __init__(self, description, enabled, environmentVariables, nodeExecutable, workingSubdirectory,
                 gruntCliExecutable, gruntfile, task):
        self.description = description
        self.enabled = enabled
        self.environmentVariables = environmentVariables
        self.nodeExecutable = nodeExecutable
        self.workingSubdirectory = workingSubdirectory
        self.gruntCliExecutable = gruntCliExecutable
        self.gruntfile = gruntfile
        self.task = task
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_language(self):
        return ('node_js')
    def get_jobs(self):
        grunt_options = []
        if self.gruntFile:
            grunt_options.append('--gruntfile "%s"' % (self.gruntFile))
        grunt_cmd = 'grunt %s%s' % (grunt_options and ('%s ' % ' '.join(grunt_options)) or '', self.task)
        return {'script': self.wrap_command(grunt_cmd)}


class CommandTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.CommandTaskProperties'
    def __init__(self, description, enabled, argument, environmentVariables, executable, workingSubdirectory):
        self.description = description
        self.enabled = enabled
        self.argument = argument
        self.environmentVariables = environmentVariables
        self.executable = executable
        self.workingSubdirectory = workingSubdirectory
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        script_cmd = ('%s %s' % (self.executable, self.argument)).strip()
        return {'script': self.wrap_command(script_cmd, self.workingSubdirectory, self.environmentVariables)}


class MochaParserTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.MochaParserTaskProperties'
    def get_language(self):
        return ('node_js')
    def get_jobs(self):
        return {'script': 'echo "Mocha task"'}


class DumpVariablesTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.DumpVariablesTaskProperties'
    def get_jobs(self):
        return {'script': 'env'}


class AnyTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.task.AnyTaskProperties'
    def __init__(self, description, enabled, atlassianPlugin, configuration):
        self.description = description
        self.enabled = enabled
        self.atlassianPlugin = atlassianPlugin
        self.configuration = configuration
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        plugin_key = self.atlassianPlugin['completeModuleKey']
        if plugin_key == 'com.davidehringer.atlassian.bamboo.maven.maven-pom-parser-plugin:maven-pom-parser-plugin':
            bamboo_prefix = 'bamboo.%s' % (self.configuration['customPrefix'] if self.configuration['prefixOption'] == '0' else 'maven.')
            maven_variables = ['groupId', 'artifactId', 'version']
            maven_cmd = 'mvn help:evaluate --non-recursive'
            if self.configuration.get('stripSnapshot', ''):
                maven_cmd = 'mvn help:evaluate --non-recursive | sed \'s/-SNAPSHOT//g\''
            if self.configuration.get('gavOrCustom', '0') != '0':
                raise UnsupportedTaskConfiguration('Specifying specific elements is not supported')
            if self.configuration.get('variableType', '0') != '0':
                raise UnsupportedTaskConfiguration('Exporting variables outside the plan is not supported')
            cmds = ['export %s=`echo \'${project.groupId}\' | %s | grep -v "^\\\\["`' % (self._convert_variable_assignments(bamboo_prefix + variable_name), maven_cmd) for variable_name in maven_variables]
        else:
            raise UnsupportedTaskConfiguration('Unsupported plugin %s' % (plugin_key))
        return {'script': cmds}


class InjectVariablesTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.InjectVariablesTaskProperties'
    def __init__(self, description, enabled, namespace, path, scope):
        self.description = description
        self.enabled = enabled
        self.namespace = namespace
        self.path = path
        self.scope = scope
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        temp_file = '$TMPDIR/bamboo-inject.properties'
        export_prefix = 'export bamboo.%s.' % (self.namespace)
        cat_cmd = 'cat "%s" | sed -e "s/^/%s/g" -e "s/\\\\./_/g" > "%s"' % (self.path, export_prefix, temp_file)
        source_cmd = 'source "%s"' % (temp_file)
        return {'script': [cat_cmd, source_cmd]}


class DockerBuildImageTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.docker.DockerBuildImageTaskProperties'
    def __init__(self, description, enabled, environmentVariables, workingSubdirectory, dockerfile, dockerfileContent,
                 imageFilename, imageName, saveAsFile, useCache):
        self.description = description
        self.enabled = enabled
        self.environmentVariables = environmentVariables
        self.workingSubdirectory = workingSubdirectory
        self.dockerfile = dockerfile
        self.dockerfileContent = dockerfileContent
        self.imageFilename = imageFilename
        self.imageName = imageName
        self.saveAsFile = saveAsFile
        self.useCache = useCache
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_services(self):
        return ['docker']
    def get_jobs(self):
        docker_opts = []
        if self.dockerfile:
            docker_opts.append('--file "%s"' % (self.dockerfile,))
        if self.imageName:
            docker_opts.append('--tag "%s"' % (self.imageName,))
        script_cmd = ('docker build %s' % (' '.join(docker_opts),)).strip()
        if self.dockerfileContent == 'INLINE':
            pushd_cmd = ('pushd "%s" && ' % (self.workingSubdirectory,)) if self.workingSubdirectory else ''
            popd_cmd = '&& popd' if self.workingSubdirectory else ''
            cmd_lines = [('%s%s echo "$(cat <<\'EOF\'' % (pushd_cmd, self._convert_variable_names(self.environmentVariables or ''))).strip()]
            cmd_lines += self.dockerfile.splitlines()
            cmd_lines += ['EOF', (') | %s" %s' % (popd_cmd,)).strip()]
            return [('script', cmd_lines)]
        elif self.dockerfileContent == 'FILE':
            return {'script': self.wrap_command(script_cmd, self.workingSubdirectory, self.environmentVariables)}


class DockerRegistryTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.docker.DockerRegistryTaskProperties'
    def __init__(self, description, enabled, environmentVariables, workingSubdirectory, email, image, operationType,
                 password, registryType, username):
        self.description = description
        self.enabled = enabled
        self.environmentVariables = environmentVariables
        self.workingSubdirectory = workingSubdirectory
        self.email = email
        self.image = image
        self.operationType = operationType
        self.password = password
        self.registryType = registryType
        self.username = username
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_services(self):
        return ['docker']
    def get_jobs(self):
        operation = self.operationType.lower()
        script_cmd = 'echo "docker %s %s"' % (operation, self.image)
        return {'script': self.wrap_command(script_cmd, self.workingSubdirectory, self.environmentVariables)}


class DockerRunContainerTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.docker.DockerRunContainerTaskProperties'
    def __init__(self, description, enabled, environmentVariables, workingSubdirectory, additionalArguments,
                 containerCommand, containerEnvironmentVariables, containerName, containerWorkingDirectory,
                 detachedContainer, imageName, linkToDetachedContainers, portMappings, serviceTimeout, serviceURLPattern,
                 volumeMappings, waitToStart):
        self.description = description
        self.enabled = enabled
        self.environmentVariables = environmentVariables
        self.workingSubdirectory = workingSubdirectory
        self.additionalArguments = additionalArguments
        self.containerCommand = containerCommand
        self.containerEnvironmentVariables = containerEnvironmentVariables
        self.containerName = containerName
        self.containerWorkingDirectory = containerWorkingDirectory
        self.detachedContainer = detachedContainer
        self.imageName = imageName
        self.linkToDetachedContainers = linkToDetachedContainers
        self.portMappings = portMappings
        self.serviceTimeout = serviceTimeout
        self.serviceURLPattern = serviceURLPattern
        self.volumeMappings = volumeMappings
        self.waitToStart = waitToStart
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_services(self):
        return ['docker']
    def get_jobs(self):
        docker_opts = []
        if self.detachedContainer:
            docker_opts.append('-d')
        if self.portMappings:
            for hostPort, containerPort in self.portMappings.items():
                docker_opts.append('-p %s:%s' % (hostPort, containerPort))
        if self.volumeMappings:
            for hostPath, containerPath in self.volumeMappings.items():
                docker_opts.append('-p %s:%s' % (hostPath, containerPath))
        if self.containerEnvironmentVariables.strip():
            for variable in self.containerEnvironmentVariables.strip().split(' '):
                docker_opts.append('-e %s' % (self._convert_variable_names(variable),))
        if self.containerWorkingDirectory:
            docker_opts.append('-w %s' % (self.containerWorkingDirectory,))
        if self.additionalArguments:
            docker_opts.append(self.additionalArguments)
        docker_cmd = ('docker run %s' % (' '.join(docker_opts),)).strip()
        script_cmd = ('%s %s %s' % (docker_cmd, self._convert_variable_names(self.imageName), self._convert_variable_names(self.containerCommand))).strip()
        return {'script': self.wrap_command(script_cmd, self.workingSubdirectory, self.environmentVariables)}


class TestParserTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.TestParserTaskProperties'
    def __init__(self, description, enabled, pickUpTestResultsCreatedOutsideOfThisBuild, resultDirectories, testType):
        self.description = description
        self.enabled = enabled
        self.pickUpTestResultsCreatedOutsideOfThisBuild = pickUpTestResultsCreatedOutsideOfThisBuild
        self.resultDirectories = resultDirectories
        self.testType = testType
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_jobs(self):
        return {'script': 'echo "Parse test results task %s"' % (self.resultDirectories)}


class SshTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.SshTaskProperties'
    def __init__(self, description, enabled, authenticationType, host, hostFingerprint, key, passphrase, password, port,
        username, command, keepAliveIntervalInSec):
        self.description = description
        self.enabled = enabled
        self.authenticationType = authenticationType
        self.host = host
        self.hostFingerprint = hostFingerprint
        self.key = key
        self.passphrase = passphrase
        self.password = password
        self.port = port
        self.username = username
        self.command = command
        self.keepAliveIntervalInSec = keepAliveIntervalInSec
    def get_jobs(self):
        ssh_opts = ''
        ssh_dest = '%s' % (self.host or 'localhost',)
        ssh_user = self.username
        if ssh_user and self.password:
            ssh_user = '%s:%s' % (ssh_user, self.password)
        if ssh_user:
            ssh_dest = '%s@%s' % (ssh_user, ssh_dest)
        if self.key:
            ssh_opts += ' -i %s' % (self.key)
        ssh_cmd = ('ssh %s "%s" "%s"' % (ssh_opts.strip(), ssh_dest.strip(), self.command or '')).strip()
        return {'script': ssh_cmd}


class NpmTaskProperties(BambooTaskProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.task.NpmTaskProperties'
    def __init__(self, description, enabled, environmentVariables, nodeExecutable, workingSubdirectory, command,
                 useIsolatedCache):
        self.description = description
        self.enabled = enabled
        self.environmentVariables = environmentVariables
        self.nodeExecutable = nodeExecutable
        self.workingSubdirectory = workingSubdirectory
        self.command = command
        self.useIsolatedCache = useIsolatedCache
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)
    def get_language(self):
        return ('node_js', self.nodeExecutable)
    def get_jobs(self):
        npm_cmd = ('npm %s' % (self.command)).strip()
        return {'script': self.wrap_command(npm_cmd, self.workingSubdirectory, self.environmentVariables)}


class ScheduledTriggerProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.trigger.ScheduledTriggerProperties'
    def __init__(self, description, enabled, name, artifactBranch, container, cronExpression):
        self.description = description
        self.enabled = enabled
        self.name = name
        self.artifactBranch = artifactBranch
        self.container = container
        self.cronExpression = cronExpression
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)


class RemoteTriggerProperties(BambooProperties):
    yaml_tag = 'tag:yaml.org,2002:com.atlassian.bamboo.specs.model.trigger.RemoteTriggerProperties'
    def __init__(self, description, enabled, name, selectedTriggeringRepositories, triggeringRepositoriesType,
                 triggerIPAddresses):
        self.description = description
        self.enabled = enabled
        self.name = name
        self.selectedTriggeringRepositories = selectedTriggeringRepositories
        self.triggeringRepositoriesType = triggeringRepositoriesType
        self.triggerIPAddresses = triggerIPAddresses
    def __repr__(self):
        return "%s(description=%r)" % (self.__class__.__name__, self.description)


def configure_yaml_loader():
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.plan.configuration.AllOtherPluginsConfigurationProperties', BambooProperties.from_yaml)

    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.trigger.RepositoryPollingTriggerProperties', BambooProperties.from_yaml)

    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.notification.BuildErrorNotificationProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.notification.EmailRecipientProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.notification.GroupRecipientProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.notification.UserRecipientProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.notification.XFailedChainsNotificationProperties', BambooProperties.from_yaml)

    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.repository.git.SshPrivateKeyAuthenticationProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.repository.git.UserPasswordAuthenticationProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.model.repository.viewer.FishEyeRepositoryViewerProperties', BambooProperties.from_yaml)

    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.repository.viewer.AnyVcsRepositoryViewerProperties', BambooProperties.from_yaml)

    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.notification.AnyNotificationRecipientProperties', BambooProperties.from_yaml)
    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.notification.AnyNotificationTypeProperties', BambooProperties.from_yaml)

    yaml.SafeLoader.add_constructor('tag:yaml.org,2002:com.atlassian.bamboo.specs.api.model.trigger.AnyTriggerProperties', BambooProperties.from_yaml)

def parse_yml(yml_file):
    try:
        build_plan = yaml.safe_load(yml_file).rootEntity
        #print('Plan %s-%s has %s repositories and %s stages' % (build_plan.project['key']['key'], build_plan.key['key'], len(build_plan.repositories), len(build_plan.stages)))
        if build_plan.enabled is True and len(build_plan.repositories) == 1:
            #print('Plan %s-%s has %s repositories and %s stages' % (build_plan.project['key']['key'], build_plan.key['key'], len(build_plan.repositories), len(build_plan.stages)))
            pass
        return build_plan
    except AttributeError as error:
        print('ERROR: Could not find rootEntity in %s' % yml_file.name)
        return None
