def doGet(request, session):
	"""Read-only control surface for the palletising cell demo.

	GET answers questions and changes nothing. Anyone on the network can ask
	it, which is what lets the 3D page poll ?cmd=state from an iframe with no
	login prompt, and what lets a test read the cell without a credential.

	    ?cmd=state                  the live cell, as the 3D page polls it
	    ?cmd=status                 a one-screen account of the whole cell
	    ?cmd=check                  report on every setup item, change nothing
	    ?cmd=faults                 the injectable faults, and what each does
	    ?cmd=alarms                 this demo's standing alarms
	    ?cmd=alarmcheck&tag=...     why an alarm is or is not standing
	    ?cmd=version                which build this gateway is running

	Everything that WRITES - setup, fix, fault, clear, reset, speed, mode,
	jog, guards - left this route deliberately. An unauthenticated GET that
	opens the guard circuit or jogs the arm is not a demonstration of access
	control, and a demo whose third pillar is security zones cannot ship one.
	Those commands live on doPost, which requires authentication, and on the
	Setup screen, which runs them in-process as the logged-in session.

	The docstring is INSIDE the def on purpose. Anything at all above
	`def doGet` in a WebDev python resource - a docstring, a comment, a blank
	line - makes the endpoint return an empty HTTP 200 with nothing in the log
	and no error anywhere.
	"""
	import traceback

	READS = ["state", "status", "version", "check", "faults", "alarms",
	         "alarmcheck"]
	WRITES = ["setup", "fix", "fault", "clear", "reset", "speed", "mode",
	          "jog", "guards"]

	params = request['params']
	cmd = params.get('cmd', 'status')

	def refuse(code, body):
		# The status code is the part a script can act on; the body is the
		# part a human reads. Both, always - a bare 403 sends the reader back
		# to the source to find out what it wanted.
		try:
			request['servletResponse'].setStatus(code)
		except:
			pass
		return {'json': body}

	try:
		if cmd == 'state':
			# The hot path: polled four times a second by the 3D cell page, so
			# it answers with the snapshot and nothing else - no wrapper, no
			# extra reads, no branch above it that could get expensive.
			return {'json': MachineDemo.api.state()}

		if cmd == 'status':
			return {'json': {'ok': True, 'status': MachineDemo.api.status()}}

		if cmd == 'version':
			return {'json': {'ok': True,
			                 'version': MachineDemo.plant.VERSION,
			                 'cell': MachineDemo.plant.CELL_NAME,
			                 'provider': MachineDemo.plant.PROVIDER,
			                 'project': system.util.getProjectName()}}

		if cmd == 'check':
			return {'json': {'ok': True, 'check': MachineDemo.setup.check()}}

		if cmd == 'faults':
			return {'json': {'ok': True, 'faults': MachineDemo.api.faults()}}

		if cmd == 'alarms':
			return {'json': {'ok': True,
			                 'counts': MachineDemo.plant.alarmCounts(),
			                 'alarms': MachineDemo.plant.liveAlarms()}}

		if cmd == 'alarmcheck':
			# Why is nothing alarming? Four different answers look identical
			# on an empty alarm table: the alarm is not defined on the tag,
			# it is defined but disabled, it is defined and enabled but the
			# value has not crossed, or it HAS crossed and queryStatus is
			# being asked the wrong question. This says which.
			prov = MachineDemo.plant.PROVIDER
			path = params.get('tag', 'Faults/ConveyorJam')
			full = MachineDemo.plant.tag(path)
			cfg = system.tag.getConfiguration(full, False)
			alarms = []
			for node in cfg:
				for a in (node.get('alarms') or []):
					alarms.append(dict((unicode(k), unicode(v))
					                   for k, v in a.items()))
			qv = system.tag.readBlocking([full])[0]
			everything = list(system.alarm.queryStatus())
			return {'json': {
				'ok': True, 'tag': path, 'value': unicode(qv.value),
				'quality': unicode(qv.quality),
				'alarmsOnTag': alarms,
				'slashTag': len(list(system.alarm.queryStatus(
					source=['prov:%s:/tag:*' % prov]))),
				'star': len(list(system.alarm.queryStatus(
					source=['prov:%s:*' % prov]))),
				'gatewayWideCount': len(everything),
				'gatewayWideSources': [unicode(e.getSource())
				                       for e in everything][:25],
			}}

		if cmd in WRITES:
			return refuse(405, {
				'ok': False,
				'error': 'writes are not accepted on GET',
				'cmd': cmd,
				'use': ('POST to this same URL with an authenticated user, '
				        'or the Setup screen in the Perspective project'),
				'example': ("curl -sS -X POST --netrc-file ~/.ignition-netrc "
				            "'.../admin?cmd=%s'" % cmd),
				'reads': READS,
				'writes': WRITES})

		return refuse(400, {'ok': False, 'error': 'unknown cmd: %s' % cmd,
		                    'reads': READS, 'writes': WRITES})

	except:
		return refuse(500, {'ok': False, 'error': traceback.format_exc()})
