import numpy as np
from typing import Dict, List, Tuple
import json

def get_target_count(usr_inputs: Dict[str, str]) -> int:
    """
    Given a dictionary of user inputs, return the number of target objectives.
    Currently, only support up to two objective.
    """
    # Initialize a counter
    i: int = 0

    # Ensure proper user inputs to form static contact angle matching objective
    assert usr_inputs.get('t1_name') == 'StaticContactAngle'
    assert usr_inputs.get('t1_mode') == 'MATCH'
    assert usr_inputs.get('t1_target') != ''
    float(usr_inputs.get('t1_target'))
    # Increment counter by 1 if proper inputs are defined
    i += 1

    # Check proper user inputs to form surfactant minimizing/maximizing
    if usr_inputs.get('t2_name') != '':
        assert usr_inputs.get('t2_name') == 'TotalSurfactantConcentration'
        if usr_inputs.get('t2_mode') == 'MATCH':
            assert usr_inputs.get('t2_target') != ''
            float(usr_inputs.get('t2_target'))
            assert usr_inputs.get('t2_transform') in ['BELL', 'TRIANGULAR']
        elif usr_inputs.get('t2_mode') in ['MIN', 'MAX']:
            assert usr_inputs.get('t2_transform') == 'LINEAR'
            bounds: str = usr_inputs.get('t2_bounds')
            bounds = bounds.strip('[]')
            b1, b2 = bounds.split(',', maxsplit=1)
            lower, upper = float(b1), float(b2)
            assert lower < upper
        # Increment counter by 1, if second objective parameters are properly defined
        i += 1
    
    # Return counter
    return i

def parse_liquid_location_input(liquid_string: str) -> Tuple[str, str]:
    """
    Parse a string and return strings representing the liquid name and concentration.
    """
    # Split the input string based on position of ':' character
    str_split: List[str] = liquid_string.split(':', maxsplit=1)
    # Check that there are only two substrings
    if len(str_split) != 2:
        raise ValueError('Invalid format for liquid name and stock concentration. Please enter <liquid_name>:<stock_concentration>')
    
    # Ensure that liquid name and concentration strings are not empty
    liquid_name, liquid_conc = str_split
    if liquid_name == '':
        raise ValueError('Invalid liquid name.')
    if liquid_conc == '':
        raise ValueError('Invalid stock concentration.')
    
    # Ensure that concentration string can be converted to float value
    float(liquid_conc)

    # Return final liquid name and concentration strings
    return liquid_name, liquid_conc

def get_liquid_locations_and_concentrations(usr_inputs: Dict[str, str]) -> Dict[str, Tuple[str, float]]:
    """
    Given a dictionary of user inputs, return a dictionary storing liquid location and concentration information.
    Output dictionary structured as {liquid_name: (well_location, liquid_concentration), ...}.
    """
    # Create a list of all possible well names [A1, A2, A3, ..., B2, B3, B4]
    # Based on calab_8_tuberack_20000ul custom labware
    well_names: List[str] = [f'A{i}' for i in range(1, 5)] + [f'B{i}' for i in range(1, 5)]

    # Create an empty dictionary
    liquid_locations_dict: Dict[str, Tuple[str, float]] = {}

    # Iterate over all well names in labware
    for well_name in well_names:
        # Ensure the user inputs is properly formated and include all available well names
        if well_name not in usr_inputs:
            raise ValueError
        
        # Get liquid string defined in user inputs
        liquid_str: str = usr_inputs[well_name]

        # If there is no liquid defined, continue to next loop iteration
        if liquid_str == '':
            continue

        # If the liquid is water, set the liquid name and concentration to 'H2O' and 100.0, respectively
        # Otherwise, parse the string input using parse_liquid_location_input() function
        if liquid_str.upper() in ['WATER', 'H2O']:
            liquid_name, liquid_conc = 'H2O', 100.0
        else:
            liquid_name, liquid_conc = parse_liquid_location_input(liquid_str)

        # Append the liquid location entry using liquid name, well name, and liquid concentration
        # Well_name is appended to a string with deck location number (i.e. 8) to get liquid location
        liquid_locations_dict.setdefault(liquid_name, (f'8-{well_name}', float(liquid_conc)))
    
    # Return the liquid location dictionary
    return liquid_locations_dict

def get_liquid_locations(usr_inputs: Dict[str, Tuple[str, float]]) -> Dict[str, Dict[str, float]]:
    """
    Given a dictionary of liquid locations and concentrations, 
    return a dictionary formatted as {liquid_name: {liquid_concentration: well_location, ...}, ...}.
    """
    # Create an empty dictionary
    liquid_locations = {}
    for k, v in usr_inputs.items():
        #liquid_name, (well_location, concentration)
        conc_locations: Dict[str, float] = liquid_locations.setdefault(k, dict())
        conc_locations[str(v[1])] = v[0]
    
    # Return formated dictionary
    return liquid_locations

def get_liquid_concentrations(usr_inputs: Dict[str, Tuple[str, float]]):
    """
    Given a dictionary of liquid locations and concentrations, 
    return a dictionary structured as as {liquid_name: [liquid_concentration], ...}.
    Currently, each unique liquid can only have one defined concentration.
    """
    # Create an empty dictionary
    liquid_concentrations = {}
    for k, v in usr_inputs.items():
        # If the liquid is water, continue to next loop iteration
        if k.upper() == 'H2O':
            continue
        liquid_concentrations.setdefault(k, [v[1]])
    
    # Return dictionary
    return liquid_concentrations

def parse_concentration_range(usr_input: str) -> Tuple[float, float, float]:
    """
    Given a string representation of a concentration range, return the start, end, and step intervals
    """
    # Strip the '[]' characters and split the string based on position of ':' characters
    input_stripped: str = usr_input.strip('[]')
    input_split: List[str] = input_stripped.split(':', maxsplit=2)

    # Return float values representing the start, end, and appropriate step intervals
    if len(input_split) == 2:
        start: float = float(input_split[0])
        end: float = float(input_split[1])
        return (start, end + 1.0, 1.0)
    
    start: float = float(input_split[0])
    end: float = float(input_split[1])
    step: float = float(input_split[2])
    return (start, end + step, step)

def get_bo_campaign_parameters(usr_inputs: Dict[str, str]) -> Dict[str, str | List[float]]:
    """
    Given a dictionary of user inputs, return a dictionary of bayesian optimization campaign parameters.
    Currently, bayesian optimization campaigns can only optimize for three reagents based on user inputs.
    """
    param_sets: List[str] = [('r1_name', 'r1_conc_0', 'r1_conc_1'), 
                             ('r2_name', 'r2_conc_0', 'r2_conc_1'), 
                             ('r3_name', 'r3_conc_0', 'r3_conc_1')]
    
    # Create an empty dictionary
    bo_parameter_dict = dict()
    # Initialize a counter
    i: int = 1
    for param_set in param_sets:
        # Get reagent names and concentration ranges
        reagent_name, conc1, conc2 = usr_inputs[param_set[0]], usr_inputs[param_set[1]], usr_inputs[param_set[2]]

        # If there is no defined reagent name, continue to next loop iteration
        if reagent_name == '':
            continue
        # If there is not valid concentration range, raise ValueError
        if conc1 == '':
            raise ValueError('Invalid concentration range. Please enter <start>:<end> or <start>:<end>:<step>')
        
        # Get the starting concentration, end concentration, and appropriate step intervals
        # Create list of reagent concentrations to test
        start, end, step = parse_concentration_range(conc1)
        concs = list(np.round(np.arange(start, end, step), 2))
        if conc2 != '':
            start, end, step = parse_concentration_range(conc2)
            concs += list(np.round(np.arange(start, end, step), 2))
        
        # Define the bayesian optimization campaign parameters
        bo_parameter_dict[f'Param{i}'] = {'Name': reagent_name,
                                          'Type':'NumericalDiscrete',
                                          'Values': concs}
        i += 1
    
    # Return dictionary of bayesian optimization campaign parameters
    return bo_parameter_dict

def get_bo_campaign_targets(usr_inputs: Dict[str, str]) -> Dict[str, str]:
    """
    Given a dictionary of user inputs, return a dictionary of bayesian optimization campaign objective target parameters.
    Currently, bayesian optimization campaigns can only optimize two objectives based on user inputs.
    """
    # Create an empty dictionary
    dic: Dict[str, str] = dict()
    # Iterate over subset of user input parameters append to dictionary
    for k in ['t1_name', 't1_target', 't1_mode', 't1_transform', 't2_name', 't2_target', 't2_mode', 't2_bounds', 't2_transform']:
        dic.setdefault(k, usr_inputs.get(k))
    # Return bayesian optimization campaign parameters
    return dic

def process_user_inputs(raise_param_form: Dict[str, str], usr_param_dir: str | None = None) -> None:
    """
    Given a dictionary of user inputs, parse the data and store individual json configuration files.
    """
    # Validate user inputs
    liquid_loc_and_conc_dict = get_liquid_locations_and_concentrations(raise_param_form)
    # Liquid locations
    liquid_locations = get_liquid_locations(liquid_loc_and_conc_dict)
    print(liquid_locations)
    # Liquid concentrations
    liquid_concentrations = get_liquid_concentrations(liquid_loc_and_conc_dict)
    print(liquid_concentrations)
    # Labware usage (n=?)
    num_replicates = int(raise_param_form['num_replicates'])
    print(f'n={num_replicates}')
    # Bayesian Optimization parameters
    bo_parameter_dict = get_bo_campaign_parameters(raise_param_form)
    if len(bo_parameter_dict) == 0:
        raise ValueError('Invalid Bayesian Optimization campaign design. No parameters defined.')
    for v in bo_parameter_dict.values():
        if v['Name'] not in liquid_locations:
            raise ValueError('Liquid in Bayesian Optimization campaign design not found in stock liquids.')
    print(bo_parameter_dict)
    # Bayesian Optimization targets
    bo_targets = get_bo_campaign_targets(raise_param_form)
    print(bo_targets)

    # Save the extracted data in individual json files.
    if usr_param_dir is not None:
        if usr_param_dir[-1] != '/':
            usr_param_dir += '/'
        fnames = ['RAISE_STATIC_CA_LIQUID_LOCATIONS.json', 
                  'RAISE_STATIC_CA_REAGENTS.json', 
                  'RAISE_STATIC_CA_LABWARE_USAGE.json', 
                  'RAISE_BO_PARAMETERS.json', 
                  'RAISE_BO_TARGETS.json']
        datas = [liquid_locations, liquid_concentrations, num_replicates, bo_parameter_dict, bo_targets]
        for fname, data in zip(fnames, datas):
            # For labware usage json, read from pre-populated file and set parameter
            # that represents number of replicate experiments to perform
            if fname == 'RAISE_STATIC_CA_LABWARE_USAGE.json':
                with open(f'./{fname}') as fd:
                    lw_usage: Dict[str, str | int] = json.load(fd)
                    lw_usage['dest_wells'] = data
                with open(f'{usr_param_dir}{fname}', mode='w') as fd:
                    json.dump(lw_usage, fd, indent=4)
                print(f'{usr_param_dir}{fname}', lw_usage)
            else:
                with open(f'{usr_param_dir}{fname}', mode='w') as fd:
                    json.dump(data, fd, indent=4)
                print(f'{usr_param_dir}{fname}', data)
    
    #return liquid_locations, liquid_concentrations, num_replicates, bo_parameter_dict, bo_targets