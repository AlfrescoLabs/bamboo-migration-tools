#!/usr/bin/python

import csv
import requests
import sys

from lib.config import get_or_create as get_or_create_config
from lib.rest import REST_CONFIG_FIELDS, api_get, api_get_paged

config = get_or_create_config('config.ini', 'bamboo', REST_CONFIG_FIELDS)
auth = (config['username'], config['password'])
base_path = config['url']
writer = csv.writer(sys.stdout)

def date_to_sheets_format(iso_date):
    return iso_date.replace('T', ' ').split('+', 1)[0].rstrip('Z')

def seconds_to_sheets_time(time_secs):
    return time_secs / (24 * 3600)

def result_row(last_result):
    plan_key = last_result['plan']['master']['key'] if 'master' in last_result['plan'] else last_result['plan']['key']
    plan_name = last_result['plan']['master']['shortName'] if 'master' in last_result['plan'] else last_result['plan']['shortName']
    branch_key = last_result['plan']['key']
    branch_name = last_result['plan']['shortName'] if 'master' in last_result['plan'] else ''
    return [plan_key, plan_name, branch_key, branch_name, last_result['plan']['enabled'], last_result['buildResultKey'], date_to_sheets_format(last_result['buildCompletedDate']), seconds_to_sheets_time(last_result['buildDurationInSeconds']), last_result['lifeCycleState'], last_result['successful'], last_result['buildReason']]

def latest_result_row(results):
    if len(results) > 0:
        return result_row(results[0])
    else:
        return None

for response_json in api_get_paged('/plan', {'expand': 'plans.plan.branches'}, 'plans', base_path=base_path, auth=auth):
    plans = response_json['plan']
    for plan in plans:
        branch_keys = [plan['key']] + [branch['key'] for branch in plan['branches']['branch']]
        for branch_key in branch_keys:
            result_resp = api_get('/result/%s' % branch_key, {'expand': 'results.result.plan'}, base_path=base_path, auth=auth).json()
            latest_row = latest_result_row(result_resp['results']['result'])
            if latest_row is not None:
                writer.writerow(latest_row)

