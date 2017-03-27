import boto3,json,imp
import pprint

def log (message):
    print id() + ": " + message

def id():
    return "eb"

def putLibratoCharts(configMap,debug):
    log("putting Librato charts for plugin : " + id())
