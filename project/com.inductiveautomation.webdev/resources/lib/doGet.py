def doGet(request, session):
	# NOTE: `def doGet` must be the first byte of this file. A docstring or even
	# a comment above it makes the route return an empty HTTP 200 with nothing
	# in the log. The explanation of what this resource is for lives in the
	# MachineDemo.assets script module instead.
	import os
	from java.lang import System

	params = request.get('params', {}) or {}
	name = params.get('f', '')

	FILES = {
		'three': ('three.min.js', 'application/javascript'),
	}

	def candidates(resource, filename):
		project = system.util.getProjectName()
		rel = os.path.join('data', 'projects', project,
		                   'com.inductiveautomation.webdev', 'resources',
		                   resource, filename)
		roots = []
		for prop in ('user.dir', 'ignition.installdir', 'catalina.base'):
			v = System.getProperty(prop)
			if v:
				roots.append(v)
				roots.append(os.path.join(v, '..'))
		roots.append('/usr/local/bin/ignition')
		out = []
		for r in roots:
			p = os.path.normpath(os.path.join(r, rel))
			if p not in out:
				out.append(p)
		return out

	if name == 'probe':
		# Which of the candidate paths actually exists on THIS gateway. Serving
		# a vendored file only works if the path resolves, and a 404 with no
		# explanation is the worst way to find out during a demonstration.
		found = []
		for p in candidates('lib', 'three.min.js'):
			found.append({'path': p, 'exists': os.path.exists(p)})
		return {'json': {'ok': True,
		                 'project': system.util.getProjectName(),
		                 'userDir': System.getProperty('user.dir'),
		                 'candidates': found}}

	if name not in FILES:
		return {'json': {'ok': False,
		                 'error': 'unknown asset',
		                 'available': sorted(FILES.keys()) + ['probe']}}

	filename, contentType = FILES[name]
	for path in candidates('lib', filename):
		if os.path.exists(path):
			body = system.file.readFileAsString(path, 'UTF-8')
			return {'contentType': contentType, 'response': body}

	return {'json': {'ok': False,
	                 'error': 'asset not found on disk',
	                 'tried': candidates('lib', filename)}}
