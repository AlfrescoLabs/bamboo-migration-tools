#!/usr/bin/python

import requests

def api_get(path, params=None, base_path=None, auth=None):
    params = params or {}
    base_path = base_path or 'http://localhost:8080/bamboo'
    r = requests.get('%s/rest/api/latest%s' % (base_path, path),
                     params=params,
                     auth=auth,
                     headers={'Accept': 'application/json'})
    r.raise_for_status()
    return r

def api_post(path, params=None, base_path=None, auth=None):
    params = params or {}
    base_path = base_path or 'http://localhost:8080/bamboo'
    r = requests.post('%s/rest/api/latest%s' % (base_path, path),
                      params=params,
                      auth=auth,
                      headers={'Accept': 'application/json'})
    r.raise_for_status()
    return r

def api_get_paged(path, params, json_key, batch_size=100, auth=None):
    offset = 0
    while True:
        try:
            api_params = dict(params)
            api_params['max-result'] = batch_size
            api_params['start-index'] = offset
            response = api_get(path, api_params, auth)
            response_data = response.json()[json_key]
            yield response_data
            offset += batch_size
            if offset >= response_data['size']:
                break
        except requests.exceptions.HTTPError as e:
            print(e)
            break

