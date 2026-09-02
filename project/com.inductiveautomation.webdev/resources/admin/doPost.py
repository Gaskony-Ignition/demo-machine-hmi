def doPost(request, session):
	"""Every command that CHANGES the cell, behind gateway authentication.

	Same URL and the same `cmd=` vocabulary the read route uses, so nothing
	about the demo has to be re-learned - only the verb changes, and with it
	the requirement to be somebody.

	    ?cmd=setup                  create everything this gateway is missing
	    ?cmd=fix&name=tags          create ONE setup item
	    ?cmd=fault&name=ConveyorJam inject one
	    ?cmd=clear&name=ConveyorJam clear one
	    ?cmd=reset                  every fault cleared, back to steady state
	    ?cmd=speed&value=3          machine time as a multiple of real time
	    ?cmd=mode&value=Manual      Auto or Manual
	    ?cmd=jog&name=down&on=1     hold a momentary jog bit (up | down)
	    ?cmd=guards&closed=0        open or close the guard circuit

	Arguments may arrive in the query string or as a JSON body; the body wins
	where both carry the same key, because a body is the harder of the two to
	send by accident.

	`require-auth` is set for doPost ONLY, in this resource's config.json.
	doGet stays open so the 3D page can poll ?cmd=state from an iframe with no
	login prompt - the split is the point.

	The docstring is INSIDE the def on purpose: anything above `def doPost`
	makes the endpoint return an empty HTTP 200 with nothing logged.
	"""
	import traceback

	WRITES = ["setup", "fix", "fault", "clear", "reset", "speed", "mode",
	          "jog", "guards"]

	args = {}
	try:
		for k, v in (request['params'] or {}).items():
			args[unicode(k)] = v
	except:
		pass
	try:
		body = request.get('data')
		if body is None:
			body = request.get('postData')
		if body is not None and hasattr(body, 'keys'):
			for k in body.keys():
				args[unicode(k)] = body[k]
	except:
		pass

	cmd = args.get('cmd', '')

	def truthy(v, default='1'):
		if v is None:
			v = default
		return unicode(v).lower() not in ('0', 'false', 'off', 'no', '')

	def refuse(code, body):
		try:
			request['servletResponse'].setStatus(code)
		except:
			pass
		return {'json': body}

	try:
		if cmd == 'setup':
			return {'json': {'ok': True, 'setup': MachineDemo.setup.run()}}

		if cmd == 'fix':
			return {'json': {'ok': True,
			                 'fixed': MachineDemo.setup.fix(
			                     args.get('name', ''))}}

		if cmd == 'fault':
			return {'json': {'ok': True,
			                 'result': MachineDemo.api.setFault(
			                     args.get('name', ''), True),
			                 'state': MachineDemo.api.state()}}

		if cmd == 'clear':
			return {'json': {'ok': True,
			                 'result': MachineDemo.api.setFault(
			                     args.get('name', ''), False),
			                 'state': MachineDemo.api.state()}}

		if cmd == 'reset':
			return {'json': {'ok': True, 'reset': MachineDemo.api.reset()}}

		if cmd == 'speed':
			return {'json': {'ok': True,
			                 'speed': MachineDemo.api.setSpeed(
			                     args.get('value', 1.0))}}

		if cmd == 'mode':
			return {'json': {'ok': True,
			                 'mode': MachineDemo.api.setMode(
			                     args.get('value', 'Auto'))}}

		if cmd == 'jog':
			return {'json': {'ok': True,
			                 'jog': MachineDemo.api.setJog(
			                     args.get('name', ''),
			                     truthy(args.get('on'), '1'))}}

		if cmd == 'guards':
			return {'json': {'ok': True,
			                 'guards': MachineDemo.api.setGuards(
			                     truthy(args.get('closed'), '1'))}}

		return refuse(400, {'ok': False,
		                    'error': 'unknown or read-only cmd: %s' % cmd,
		                    'hint': 'reads are on GET, writes are on POST',
		                    'writes': WRITES})

	except:
		return refuse(500, {'ok': False, 'error': traceback.format_exc()})
