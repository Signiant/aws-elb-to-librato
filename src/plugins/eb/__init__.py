import boto3,json,imp,pprint
from botocore.exceptions import ClientError

import librato_lb_chart

def log (message):
    print id() + ": " + message

def id():
    return "eb"

#
# For a given EB environment, get the load balancer name
#
def get_env_elb(envname,region):
    client = boto3.client('elasticbeanstalk', region_name=region)
    response = ""
    elb_name = ""

    try:
        response = client.describe_environment_resources(
            EnvironmentName=envname
        )
    except Exception, e:
        log("Error describing the EB environment resources for " + envname + " (" + str(e) + ")")

    if response:
        # Eb only uses a single load balancer so grab the first
        elb_name = response['EnvironmentResources']['LoadBalancers'][0]['Name']

    return elb_name

#
# For a given LB, see if it's an ELB or an ALB
#
def get_lb_type(lbname,region):
    lb_type = ""
    response = ""
    test_for_alb = False

    client = boto3.client('elb')

    try:
        response = client.describe_load_balancers(
            LoadBalancerNames=[
                lbname
            ]
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'LoadBalancerNotFound':
            # No ELB found but perhaps this is an ALB?
            test_for_alb = True
        else:
            log ("Error getting properties for load balancer " + lbname + " (" + str(e) + ")")

    if response:
        # If we have a repsonse, we know the load balancer was found as an ELB
        lb_type = "elb"
    elif test_for_alb:
        client = boto3.client('elbv2')

        try:
            response = client.describe_load_balancers(
                Names=[
                    lbname
                ]
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'LoadBalancerNotFound':
                # Not an ELB or an ALB....
                lb_type = "unknown"
            else:
                log("Error getting properties for load balancer " + lbname + " (" + str(e) + ")")

        if response:
            # If we have a response here, we know the load balancer was found as an ALB
            lb_type='alb'

    return lb_type

#
# Create charts in Librato for each EB environment
#
def putLibratoCharts(configMap,debug):
    if debug: log("putting Librato charts for plugin : " + id())
    if debug: pprint.pprint(configMap)

    chart_status = 0
    plugin_status = 0

    if 'aws' in configMap and configMap['aws']:
        if 'region' in configMap['aws']:
            aws_region = configMap['aws']['region']
            log("Querying resources in AWS region " + aws_region)
        else:
            aws_region = 'us-east-1'
            log("No AWS region defined in config file - defaulting to us-east-1")
    else:
        aws_region = "us-east-1"
        log("No AWS region defined in config file - defaulting to us-east-1")

    # get the list of EB envs from the configMap
    for config_plugin in configMap['plugins']:
        if config_plugin['name'] == id():
            if debug: log("plugin info found in config file")
            environments = config_plugin['environments']

            for environment in environments:
                log("processing EB env " + environment["name"])

                env_lb = get_env_elb(environment["name"],aws_region)
                if debug: log("Found LB for " + environment["name"] + " is " + env_lb)

                env_lb_type = get_lb_type(env_lb,aws_region)

                if env_lb_type != "unknown":
                    # create all our charts
                    for chart in environment['charts']:
                        log("creating chart in space " + str(chart["librato_space"]) + " of type " + chart["chart_type"])

                        chart_status = librato_lb_chart.createLibratoLBChartInSpace(env_lb,
                                                                                    env_lb_type,
                                                                                    environment["name"],
                                                                                    chart["chart_type"],
                                                                                    chart["librato_space"],
                                                                                    configMap,
                                                                                    debug)

                        if chart_status == 0:
                            log("Chart successfully created in Librato for LB " + env_lb + " with name " + environment["name"])
                        elif chart_status == 1:
                            log("Error creating a chart in Librato for LB " + env_lb + " with name " + environment["name"])
                            plugin_status = 1
                        elif chart_status == 2:
                            log("Chart already exists in Librato for LB " + env_lb + " with name " + environment["name"])
                        else:
                            log("Unknown error creating a chart in Librato for LB " + env_lb + " with name " + environment["name"])
                            plugin_status = 1

    return plugin_status
