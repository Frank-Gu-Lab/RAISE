from flask import Flask, render_template, redirect, request
import numpy as np
from typing import Dict, List, Tuple
from os.path import exists, isdir
from os import makedirs
import json

app = Flask(__name__)

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