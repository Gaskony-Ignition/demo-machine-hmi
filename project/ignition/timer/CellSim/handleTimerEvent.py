def handleTimerEvent():
	"""One simulation step, twice a second.

	500 ms is the slowest rate at which the arm still reads as a moving
	machine: the shortest phase of the cycle is 0.8 machine-seconds, so at 1x
	even that phase gets a couple of samples, and the 3D page - which polls at
	250 ms - interpolates between them.

	`sharedThread` and a FIXED DELAY: the model integrates against measured
	elapsed real time rather than tick count, so a tick that runs late makes
	the cell no less correct, only less smooth. A missed tick cannot make the
	pallet count wrong.

	MachineDemo.sim.tick() does not raise. A gateway timer whose script throws
	can stop being scheduled, and a dead demo is worse than a rough one.
	"""
	MachineDemo.sim.tick()
