from flask import Flask, render_template, redirect, request
import numpy as np
from typing import Dict, List, Tuple
from os.path import exists, isdir
from os import makedirs
import json

app = Flask(__name__)

def parse_liquid_location_input(liquid_string: str) -> Tuple[str, str]:
    str_split: List[str] = liquid_string.split(':', maxsplit=1)
    if len(str_split) != 2:
        raise ValueError
    
    liquid_name, liquid_conc = str_split
    if liquid_name == '':
        raise ValueError
    if liquid_conc == '':
        raise ValueError
    
    float(liquid_conc)

    return liquid_name, liquid_conc

def get_liquid_locations_and_concentrations(usr_inputs: Dict[str, str]) -> Dict[str, Tuple[str, float]]:
    well_names: List[str] = [f'A{i}' for i in range(1, 5)] + [f'B{i}' for i in range(1, 5)]
    liquid_locations_dict: Dict[str, Tuple[str, float]] = {}
    for well_name in well_names:
        if well_name not in usr_inputs:
            raise ValueError
        liquid_str: str = usr_inputs[well_name]

        if liquid_str == '':
            continue

        if liquid_str.upper() in ['WATER', 'H2O']:
            liquid_name, liquid_conc = 'H2O', 100.0
        else:
            liquid_name, liquid_conc = parse_liquid_location_input(liquid_str)

        liquid_locations_dict.setdefault(liquid_name, (f'8-{well_name}', float(liquid_conc)))
    return liquid_locations_dict

def get_liquid_locations(usr_inputs: Dict[str, Tuple[str, float]]):
    liquid_locations = {}
    for k, v in usr_inputs.items():
        liquid_locations.setdefault(k, v[0])
    return liquid_locations

def get_liquid_concentrations(usr_inputs: Dict[str, Tuple[str, float]]):
    liquid_concentrations = {}
    for k, v in usr_inputs.items():
        if k.upper() == 'H2O':
            continue
        liquid_concentrations.setdefault(k, [v[1]])
    return liquid_concentrations

def parse_concentration_range(usr_input: str) -> Tuple[float, float, float]:
    input_stripped: str = usr_input.strip('[]')
    input_split: List[str] = input_stripped.split(':', maxsplit=2)

    if len(input_split) == 2:
        start: float = float(input_split[0])
        end: float = float(input_split[1])
        return (start, end + 1.0, 1.0)
    
    start: float = float(input_split[0])
    end: float = float(input_split[1])
    step: float = float(input_split[2])
    return (start, end + step, step)

def get_bo_campaign_parameters(usr_inputs: Dict[str, str]) -> Dict[str, str | List[float]]:
    param_sets: List[str] = [('r1_name', 'r1_conc_0', 'r1_conc_1'), 
                             ('r2_name', 'r2_conc_0', 'r2_conc_1'), 
                             ('r3_name', 'r3_conc_0', 'r3_conc_1')]
    
    bo_parameter_dict = dict()
    i: int = 1
    for param_set in param_sets:
        reagent_name, conc1, conc2 = usr_inputs[param_set[0]], usr_inputs[param_set[1]], usr_inputs[param_set[2]]
        if reagent_name == '':
            continue
        if conc1 == '':
            raise ValueError
        
        start, end, step = parse_concentration_range(conc1)
        concs = list(np.round(np.arange(start, end, step), 2))
        if conc2 != '':
            start, end, step = parse_concentration_range(conc2)
            concs += list(np.round(np.arange(start, end, step), 2))
        
        bo_parameter_dict[f'Param{i}'] = {'Name': reagent_name,
                                          'Type':'NumericalDiscrete',
                                          'Values': concs}
        i += 1
    return bo_parameter_dict

def process_user_inputs(raise_param_form: Dict[str, str]) -> None:
    # Validate user inputs
    liquid_loc_and_conc_dict = get_liquid_locations_and_concentrations(raise_param_form)
    # liquid locations
    liquid_locations = get_liquid_locations(liquid_loc_and_conc_dict)
    print(liquid_locations)
    # liquid concentrations
    liquid_concentrations = get_liquid_concentrations(liquid_loc_and_conc_dict)
    print(liquid_concentrations)
    # labware usage (n=?)
    num_replicates = int(raise_param_form['num_replicates'])
    print(f'n={num_replicates}')
    # BO parameters
    bo_parameter_dict = get_bo_campaign_parameters(raise_param_form)
    if len(bo_parameter_dict) == 0:
        raise ValueError
    for v in bo_parameter_dict.values():
        if v['Name'] not in liquid_locations:
            raise ValueError
    print(bo_parameter_dict)
        

@app.route('/RAISE/', methods=['GET', 'POST'])
def main_paige():
    if request.method == 'POST':
        print(request.method)
        # Compile all relevant parameters to run a campaign
        raise_param_form = dict(request.form)
        raise_param_form.setdefault('t2_mode', '')
        raise_param_form.setdefault('t2_transform', '')
        print(raise_param_form)

        parameters_dir: str = './PARAMETERS/'
        if not exists(parameters_dir):
            makedirs(parameters_dir)
        with open(parameters_dir + 'USER_INPUTS.json', mode='w') as fd:
            json.dump(raise_param_form, fp=fd, indent=4)
        
    return render_template('index.html')

@app.route('/RAISE/Run_Campgaign/')
def run_campaign():
    # Implement method to quit/terminate running campaigns
    return "<h1>The RAISE Campaign is Running...</h1>"

if __name__ == '__main__':
    app.run(debug=True)