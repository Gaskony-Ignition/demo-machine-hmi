def doGet(request, session):
	# `def doGet` must be the first byte of this file - anything above it makes
	# the route return an empty 200 with nothing in the log.
	import os
	from java.lang import System

	params = request.get('params', {}) or {}
	want = params.get('f', '')

	def folder():
		project = system.util.getProjectName()
		rel = os.path.join('data', 'projects', project,
		                   'com.inductiveautomation.webdev', 'resources', 'cad')
		roots = []
		for prop in ('user.dir', 'ignition.installdir', 'catalina.base'):
			v = System.getProperty(prop)
			if v:
				roots.append(v)
				roots.append(os.path.join(v, '..'))
		roots.append('/usr/local/bin/ignition')
		for r in roots:
			p = os.path.normpath(os.path.join(r, rel))
			if os.path.isdir(p):
				return p
		return None

	d = folder()
	if d is None:
		return {'json': {'ok': False, 'error': 'cad folder not found'}}

	# Whatever STL files are sitting in this resource folder ARE the model.
	# Adding a part is dropping a file in and running a project scan; there is
	# no list to maintain in here.
	names = sorted([f[:-4] for f in os.listdir(d) if f.lower().endswith('.stl')])

	if want == 'list':
		return {'json': {'ok': True, 'parts': names,
		                 'project': system.util.getProjectName()}}

	if want in names:
		p = os.path.join(d, '%s.stl' % want)
		# Returning the byte[] as 'response' does NOT work - WebDev encodes it
		# as text and a 28,984-byte STL arrives as 39,156 bytes of mojibake,
		# with no error anywhere. Measured 09/09/2026. Write the bytes to the
		# servlet stream instead and return nothing.
		data = system.file.readFileAsBytes(p)
		resp = request['servletResponse']
		resp.setContentType('application/octet-stream')
		resp.setContentLength(len(data))
		out = resp.getOutputStream()
		out.write(data)
		out.flush()
		return None

	return {'json': {'ok': False, 'error': 'unknown part',
	                 'available': names + ['list']}}
