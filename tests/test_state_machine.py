from dicton.core.state_machine import SessionEvent, SessionState, SessionStateMachine


def test_state_machine_happy_path():
    sm = SessionStateMachine()
    assert sm.state == SessionState.IDLE

    sm.transition(SessionEvent.START)
    assert sm.state == SessionState.RECORDING

    sm.transition(SessionEvent.STOP)
    assert sm.state == SessionState.PROCESSING

    sm.transition(SessionEvent.PROCESS_DONE)
    assert sm.state == SessionState.OUTPUTTING

    sm.transition(SessionEvent.OUTPUT_DONE)
    assert sm.state == SessionState.IDLE


def test_state_machine_error_reset():
    sm = SessionStateMachine()
    sm.transition(SessionEvent.START)
    sm.transition(SessionEvent.ERROR)
    assert sm.state == SessionState.ERROR

    sm.transition(SessionEvent.RESET)
    assert sm.state == SessionState.IDLE


def test_cancel_from_processing():
    sm = SessionStateMachine()
    sm.transition(SessionEvent.START)
    sm.transition(SessionEvent.STOP)
    assert sm.state == SessionState.PROCESSING

    sm.transition(SessionEvent.CANCEL)
    assert sm.state == SessionState.IDLE


def test_cancel_from_outputting():
    sm = SessionStateMachine()
    sm.transition(SessionEvent.START)
    sm.transition(SessionEvent.STOP)
    sm.transition(SessionEvent.PROCESS_DONE)
    assert sm.state == SessionState.OUTPUTTING

    sm.transition(SessionEvent.CANCEL)
    assert sm.state == SessionState.IDLE
