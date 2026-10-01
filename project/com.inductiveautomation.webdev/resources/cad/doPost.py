def doPost(request, session):
	# `def doPost` must be the first byte of this file.
	# The only write here: the part names the CAD page parsed out of a STEP
	# model, so the simulate-alarm popup can offer them. MachineDemo.cad
	# .saveParts accepts a list of names for an existing STEP model, nothing
	# else; tags are never written over HTTP.
	params = request.get('params', {}) or {}
	if params.get('f', '') != 'parts' or not params.get('model'):
		return {'json': {'ok': False, 'error': 'only ?f=parts&model=<name> is accepted'}}
	try:
		n = MachineDemo.cad.saveParts(params.get('model'), request.get('postData'))
	except ValueError as e:
		return {'json': {'ok': False, 'error': str(e)}}
	return {'json': {'ok': True, 'parts': n}}
