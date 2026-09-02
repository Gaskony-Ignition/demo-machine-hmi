def doGet(request, session):
	"""Headless control surface for the palletising cell demo.

	It exists so the cell can be installed, driven and proved without a browser
	or a Designer - which is what makes it testable from a script, and drivable
	from a phone in the middle of a meeting.

	    ?cmd=state                  the live cell, as the 3D page polls it
	    ?cmd=status                 a one-screen account of the whole cell
	    ?cmd=setup                  create everything this gateway is missing
	    ?cmd=check                  report on every setup item, change nothing
	    ?cmd=fix&name=tags          create ONE setup item
	    ?cmd=faults                 the injectable faults, and what each does
	    ?cmd=fault&name=ConveyorJam inject one
	    ?cmd=clear&name=ConveyorJam clear one
	    ?cmd=jog&name=down&on=1     hold a momentary jog bit (up | down)
	    ?cmd=guards&closed=0        open or close the guard circuit
	    ?cmd=reset                  every fault cleared, back to steady state
	    ?cmd=speed&value=3          machine time as a multiple of real time
	    ?cmd=mode&value=Manual      Auto or Manual
	    ?cmd=alarms                 this demo's standing alarms
	    ?cmd=version                which build this gateway is running

	The docstring is INSIDE the def on purpose. Anything at all above
	`def doGet` in a WebDev python resource - a docstring, a comment, a blank
	line - makes the endpoint return an empty HTTP 200 with nothing in the log
	and no error anywhere.
	"""
	import traceback

	params = request['params']
	cmd = params.get('cmd', 'status')

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

		if cmd == 'setup':
			return {'json': {'ok': True, 'setup': MachineDemo.setup.run()}}

		if cmd == 'fix':
			name = params.get('name', '')
			return {'json': {'ok': True,
			                 'fixed': MachineDemo.setup.fix(name)}}

		if cmd == 'faults':
			return {'json': {'ok': True, 'faults': MachineDemo.api.faults()}}

		if cmd == 'fault':
			return {'json': {'ok': True,
			                 'result': MachineDemo.api.setFault(
			                     params.get('name', ''), True),
			                 'state': MachineDemo.api.state()}}

		if cmd == 'clear':
			return {'json': {'ok': True,
			                 'result': MachineDemo.api.setFault(
			                     params.get('name', ''), False),
			                 'state': MachineDemo.api.state()}}

		if cmd == 'reset':
			return {'json': {'ok': True, 'reset': MachineDemo.api.reset()}}

		if cmd == 'speed':
			return {'json': {'ok': True,
			                 'speed': MachineDemo.api.setSpeed(
			                     params.get('value', 1.0))}}

		if cmd == 'mode':
			return {'json': {'ok': True,
			                 'mode': MachineDemo.api.setMode(
			                     params.get('value', 'Auto'))}}

		if cmd == 'jog':
			# ?cmd=jog&name=up|down&on=1|0 - writes the momentary bit only.
			on = params.get('on', '1')
			on = unicode(on).lower() not in ('0', 'false', 'off', 'no')
			return {'json': {'ok': True,
			                 'jog': MachineDemo.api.setJog(
			                     params.get('name', ''), on)}}

		if cmd == 'guards':
			closed = params.get('closed', '1')
			closed = unicode(closed).lower() not in ('0', 'false', 'off', 'no')
			return {'json': {'ok': True,
			                 'guards': MachineDemo.api.setGuards(closed)}}

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

		return {'json': {'ok': False, 'error': 'unknown cmd: %s' % cmd,
		                 'commands': ['state', 'status', 'setup', 'check',
		                              'fix', 'faults', 'fault', 'clear',
		                              'reset', 'speed', 'mode', 'alarms',
		                              'jog', 'guards', 'version']}}

	except:
		return {'json': {'ok': False, 'error': traceback.format_exc()}}
