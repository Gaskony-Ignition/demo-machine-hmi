def doGet(request, session):
	# `def doGet` must be the first byte of this file - a docstring or comment
	# above it makes the route return an empty HTTP 200 with nothing logged.
	#
	# Serves the 3D palletising cell page. The page itself is page.html beside
	# this file, kept as a real .html file rather than a string in here so it
	# stays editable, diffable and lintable.
	import os
	from java.lang import System

	def resolve(resource, filename):
		project = system.util.getProjectName()
		rel = os.path.join('data', 'projects', project,
		                   'com.inductiveautomation.webdev', 'resources',
		                   resource, filename)
		roots = []
		for prop in ('user.dir', 'ignition.installdir'):
			v = System.getProperty(prop)
			if v:
				roots.append(v)
				roots.append(os.path.join(v, '..'))
		roots.append('/usr/local/bin/ignition')
		tried = []
		for r in roots:
			p = os.path.normpath(os.path.join(r, rel))
			if p in tried:
				continue
			tried.append(p)
			if os.path.exists(p):
				return p, tried
		return None, tried

	path, tried = resolve('cell3d', 'page.html')
	if path is None:
		return {'html': (
			'<html><body style="background:#171b20;color:#ff8d92;'
			'font-family:sans-serif;padding:40px">'
			'<h2>3D cell page not found on disk</h2><pre>%s</pre>'
			'</body></html>' % '\n'.join(tried))}

	return {'contentType': 'text/html;charset=utf-8',
	        'response': system.file.readFileAsString(path, 'UTF-8')}
