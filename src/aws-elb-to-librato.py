import librato
import argparse
import os,sys
import json,yaml
import pprint
import boto3

# Project modules
import plugin

def readConfigFile(path):
    configMap = []

    try:
        config_file_handle = open(path)
        configMap = yaml.load(config_file_handle)
        config_file_handle.close()
    except:
        print "Error: Unable to open config file %s or invalid yaml" % path

    return configMap

## mainFile
def main(argv):
    plugin_results = dict()

    # Add our folder to the system path
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    parser = argparse.ArgumentParser(description='Create charts in Librato')
    parser.add_argument('-d','--debug', help='Enable debug output',action='store_true')
    parser.add_argument('-c','--config', help='Full path to a config file',required=True)

    args = parser.parse_args()

    configMap = readConfigFile(args.config)

    if configMap:
        # Invoke each of the plugins and store the results
        for config_plugin in configMap['plugins']:
            plugin_name = config_plugin['name']
            print "Loading plugin %s" % plugin_name

            # Load the plugin from the plugins folder
            plugin_handle = plugin.loadPlugin(plugin_name)

            # Store the plugin output in a dict
            plugin_results[plugin_name] = plugin_handle.putLibratoCharts(configMap,args.debug)

if __name__ == "__main__":
   main(sys.argv[1:])
