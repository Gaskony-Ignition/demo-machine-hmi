def doGet(request, session):
	# `def doGet` must be the first byte of this file - anything above it makes
	# the route return an empty 200 with nothing in the log.
	import os

	params = request.get('params', {}) or {}
	want = params.get('f', '')
	model = params.get('model', '') or ''

	def send(path, contentType):
		# Returning the byte[] as 'response' does NOT work - WebDev encodes it
		# as text and a 28,984-byte STL arrives as 39,156 bytes of mojibake,
		# with no error anywhere. Measured 09/09/2026. Write the bytes to the
		# servlet stream instead and return nothing.
		data = system.file.readFileAsBytes(path)
		resp = request['servletResponse']
		resp.setContentType(contentType)
		resp.setContentLength(len(data))
		out = resp.getOutputStream()
		out.write(data)
		out.flush()
		return None

	if want == 'alarms':
		return {'json': {'ok': True, 'key': MachineDemo.tagdata.CAD_PART,
		                 'alarms': MachineDemo.cad.alarms()}}

	if model:
		try:
			kind, names = MachineDemo.cad.files(model)
		except ValueError as e:
			return {'json': {'ok': False, 'error': str(e)}}
		if want == 'list':
			return {'json': {'ok': True, 'model': model, 'kind': kind,
			                 'parts': names}}
		path = MachineDemo.cad.filePath(model, want) if want in names else None
		if path is None:
			return {'json': {'ok': False, 'error': 'unknown part',
			                 'available': names + ['list']}}
		return send(path, 'application/octet-stream')

	d = MachineDemo.cad.builtinDir()
	if d is None:
		return {'json': {'ok': False, 'error': 'cad folder not found'}}

	# Whatever STL files are sitting in this resource folder ARE the built-in
	# model. Adding a part is dropping a file in and running a project scan;
	# there is no list to maintain in here.
	names = sorted([f[:-4] for f in os.listdir(d) if f.lower().endswith('.stl')])

	if want == 'list':
		return {'json': {'ok': True, 'kind': 'stl', 'parts': names,
		                 'project': system.util.getProjectName()}}

	if want in names:
		return send(os.path.join(d, '%s.stl' % want), 'application/octet-stream')

	return {'json': {'ok': False, 'error': 'unknown part',
	                 'available': names + ['list', 'alarms']}}
