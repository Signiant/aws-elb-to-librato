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

    client = boto3.client('elb', region_name=region)

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
        client = boto3.client('elbv2', region_name=region)

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
# Is this EB load balancer currently "live"?
#
def is_current_eb_env_live(env_lb,switchable_dns_entry,zoneid,region):
    isLive = False

    current_live_elb = get_r53_alias_entry(switchable_dns_entry, zoneid).rstrip('.').lower()

    if current_live_elb.startswith(env_lb.lower()):
        isLive = True

    return isLive

#
# Get the route53 Alias entry for a given name
#
def get_r53_alias_entry(query_name,zoneid):
    endpoint = ""

    client = boto3.client('route53')

    response = client.list_resource_record_sets(
        HostedZoneId=zoneid,
        StartRecordName=query_name,
        StartRecordType='A',
        MaxItems='1'
    )

    if response:
        endpoint = response['ResourceRecordSets'][0]['AliasTarget']['DNSName']

    return endpoint

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

    librato_creds = librato_lb_chart.getLibratoCredentials(configMap)

    # get the list of EB envs from the configMap
    for config_plugin in configMap['plugins']:
        if config_plugin['name'] == id():
            if debug: log("plugin info found in config file")
            environments = config_plugin['environments']

            for environment in environments:
                log("processing EB env " + environment["name"])

                # Set the default threshold values for this chart
                # TODO: Make this configurable in this plugin
                red_threshold_val = 99.95
                yellow_threshold_val = 99.97
                log("Using chart thresholds of red: %s yellow %s" % (str(red_threshold_val),str(yellow_threshold_val)))

                env_lb = get_env_elb(environment["name"],aws_region)
                if debug: log("Found LB for " + environment["name"] + " is " + env_lb)

                env_lb_type = get_lb_type(env_lb,aws_region)

                if env_lb_type != "unknown":
                    # create all our charts
                    for chart in environment['charts']:
                        # Should we be adding a chart or deleting one?
                        # We only want to show a chart for the currently live environment
                        log("Determining if we need to show a chart for " + environment["name"])

                        # env_lb,switchable_dns_entry,zoneid,region
                        if is_current_eb_env_live(env_lb,environment["route53"]["switchable_dns"],environment["route53"]["zoneid"],aws_region):
                            # we need a chart for this one
                            log("Environment " + environment["name"] + " is live. Creating chart in space " + str(chart["librato_space"]) + " of type " + chart[
                                "chart_type"])

                            if 'deploy_feed' in chart:
                                log("Found a deployment feed for this chart - will add to streams")
                                deployments_stream_name = chart["deploy_feed"]
                            else:
                                deployments_stream_name = ""

                            chart_status = librato_lb_chart.createLibratoLBChartInSpace(env_lb,
                                                                                        env_lb_type,
                                                                                        environment["name"],
                                                                                        chart["chart_type"],
                                                                                        chart["librato_space"],
                                                                                        red_threshold_val,
                                                                                        yellow_threshold_val,
                                                                                        deployments_stream_name,
                                                                                        configMap,
                                                                                        debug)

                            if chart_status == 0:
                                log("Chart successfully created in Librato for LB " + env_lb + " with name " +
                                    environment["name"])
                            elif chart_status == 1:
                                log("Error creating a chart in Librato for LB " + env_lb + " with name " + environment[
                                    "name"])
                                plugin_status = 1
                            elif chart_status == 2:
                                log("Chart already exists in Librato for LB " + env_lb + " with name " + environment[
                                    "name"])
                            else:
                                log("Unknown error creating a chart in Librato for LB " + env_lb + " with name " +
                                    environment["name"])
                                plugin_status = 1
                        else:
                            log("Environment " + environment["name"] + " is not live...not creating chart or deleting existing chart")
                            chart_id = librato_lb_chart.doesChartExist(env_lb, chart["librato_space"], environment["name"], librato_creds, debug)

                            if chart_id != 0:
                                if librato_lb_chart.deleteChart(chart_id, chart["librato_space"], librato_creds, debug) == 0:
                                    log("Deleted chart " + str(chart_id) + " from space " + str(chart["librato_space"]))
                                else:
                                    log("Error: Unable to delete chart " + str(chart_id) + " from space " + str(chart["librato_space"]))
                                    plugin_status = 1

    return plugin_status
