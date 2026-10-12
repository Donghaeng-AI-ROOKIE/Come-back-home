"""Clearer presentation of supplied simulator facts, without selecting actions.

No guardian-text parsing. Event ages are arithmetic on typed simulation times.
This is prepared for a new experiment, not used to change the frozen c5 results.
"""
from copy import deepcopy
import math


def presentation(context):
    state=context['state'];now=state['elapsed_minutes']
    if not math.isfinite(now) or now<0:raise ValueError('invalid current simulation time')
    events=[]
    for event in state.get('recent_events',[]):
        event=deepcopy(event);minute=event.get('elapsed_minutes')
        if minute is None or not math.isfinite(minute) or not 0<=minute<=now:
            raise ValueError('invalid event timestamp')
        event['occurred_at_simulation_minute']=minute
        event['minutes_before_current_decision']=now-minute
        events.append(event)
    last_rest=state.get('last_rest_end_minutes')
    if last_rest is not None and (not math.isfinite(last_rest) or not 0<=last_rest<=now):
        raise ValueError('invalid rest timestamp')
    return {
        'guardian_and_person':deepcopy(context['person']),
        'registered_destinations':deepcopy(context['known_places']),
        'current_decision':{
            'wall_clock_time':context['clock_time'],
            'elapsed_simulation_minutes':now,
            'fatigue':state['fatigue'],
            'confusion':state['confusion'],
            'anxiety':state.get('anxiety'),
            'distance_already_walked_m':state['distance_m'],
            'target_already_reached':state['target_reached'],
            'minutes_since_last_rest_completed':None if last_rest is None else now-last_rest,
            'rest_completion_does_not_imply_full_recovery':True,
        },
        'previous_execution_not_a_new_instruction':{
            'action':state['current_action'],'target':state['target_label'],
            'notice':'Previous action/goal may change when a personal condition currently applies.'},
        'simulated_events_not_real_patient_observations':events,
        'environment_facts_supplied_by_simulator':deepcopy(context['environment']),
        'research':deepcopy(context['research']),
        'limitations':deepcopy(context.get('limitations',[])),
    }
