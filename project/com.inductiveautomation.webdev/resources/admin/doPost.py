def doPost(request, session):
	"""POST no longer writes anything - this route was retired.

	Every command that used to accept a POST here - setup, fix, fault, clear,
	reset, speed, mode, jog, guards - now goes through one of two places
	instead: the Setup screen, which calls MachineDemo.api.* and
	MachineDemo.setup.* in gateway scope as the signed-in Perspective session,
	or the Designer's Script Console, which calls the same functions
	directly. Nothing on the network can write to this cell any more - not
	with a credential, not without one - because the write path itself is
	gone, not just guarded.

	That is a portability choice, not a security one. The old check was HTTP
	Basic against a named user source (`doPost.user-source`, which shipped as
	`temp` - this gateway's own name), and it answered 500 on any other
	gateway that lacked one. Removing the write path instead of naming a
	source means the project ships with nothing gateway-specific in it and
	nothing left to configure or protect - every POST this route receives
	gets the same refusal, credentialed or not.

	doGet is unaffected: reads stay open, still no credential, still the same
	405 for a write `cmd` arriving on GET.

	The docstring is INSIDE the def on purpose. Anything above `def doPost` -
	a docstring, a comment, a blank line - makes the endpoint return an empty
	HTTP 200 with nothing in the log and no error anywhere.
	"""
	import traceback

	def refuse(code, body):
		# The status code is the part a script can act on; the body is the
		# part a human reads. Both, always.
		try:
			request['servletResponse'].setStatus(code)
		except:
			pass
		return {'json': body}

	try:
		cmd = (request['params'] or {}).get('cmd', '')
		return refuse(405, {
			'ok': False,
			'error': ('writes are not accepted over HTTP; use the Setup '
			          'screen or the Designer Script Console'),
			'cmd': cmd,
			'use': ('MachineDemo.api.* / MachineDemo.setup.* from the '
			        'Designer Script Console, or the Setup screen in the '
			        'Perspective project'),
		})

	except:
		return refuse(500, {'ok': False, 'error': traceback.format_exc()})
