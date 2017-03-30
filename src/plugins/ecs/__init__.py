import boto3,json,imp
import pprint

import librato_lb_chart

def log (message):
    print id() + ": " + message

def id():
    return "ecs"

#
# Given a target group, see which ALB it is assigned to
#
def findALBForTargetGroup(target_group_arn,region,debug):
    alb_name = ""

    client = boto3.client('elbv2', region_name=region)

    # This whole process kinda violates the schema since a target group can be associated with
    # multiple ALBs.  However, in our case that's not the case
    try:
        response = client.describe_target_groups(
            TargetGroupArns=[
                target_group_arn
            ],
        )
    except Exception as e:
        log("Error obtaining info for target group " + target_group_arn + " (" + str(e) + ")")

    if response:
        # get ARN of the first load balancer for this target group
        lb_arn = response['TargetGroups'][0]['LoadBalancerArns'][0]

        # ALB metrics are really weird. Rather than using the LB name, they use a part of the ARN in cloudwatch
        # It turns out we need 'app/<LB NAME>/<GUID>
        # and there is no way to get this other then parsing the ARN
        alb_name = lb_arn.split("loadbalancer/")[1]

        if debug: log("ALB name determined to be " + alb_name)

    return alb_name

def getECSServices(cluster_name,region,debug):
    services = []
    service_iterator = ""
    ecs_service = dict()

    client = boto3.client('ecs',region_name=region)

    # This needs to used pagination because the max results returned is 10
    try:
        service_paginator = client.get_paginator('list_services')
        service_iterator = service_paginator.paginate(cluster=cluster_name)
    except Exception, e:
        log("Error obtaining list of ECS services for " + cluster_name + " (" + str(e) + ")")

    # Need to loop over the results because they come back in multiple batches/pages
    if service_iterator:
        for service in service_iterator:
            # Get the service info for each batch
            services_descriptions = client.describe_services(cluster=cluster_name, services=service['serviceArns'])

            for service_desc in services_descriptions['services']:

                # Get the friendly name. Use the docker image name
                friendly_name = ""
                image = client.describe_task_definition(taskDefinition=service_desc['taskDefinition'])

                if image:
                    friendly_name = image['taskDefinition']['containerDefinitions'][0]['image'].split(':')[0].split('/')[1]

                # Get the load balancer for this service
                lb_name = ""
                lb_type = ""

                if 'loadBalancers' in service_desc:
                    # There should only be 1 LB despite the schema allowing multiple
                    # get the first.
                    for lb in service_desc['loadBalancers']:
                        if 'loadBalancerName' in lb:
                            lb_name = lb['loadBalancerName']
                            lb_type = "elb"
                            break
                        elif 'targetGroupArn' in lb:
                            lb_name = findALBForTargetGroup(lb['targetGroupArn'],region,debug)
                            lb_type = "alb"
                            break
                        else:
                            log("Service " + friendly_name + " is using an unknown load balancer type")
                            lb_name = ""
                            lb_type = ""
                            break

                log("Load balancer name for service " + friendly_name + " is " + lb_name + " type: " + lb_type)

                if lb_name and lb_type and friendly_name:
                    ecs_service['friendly_name'] = friendly_name
                    ecs_service['lb_name'] = lb_name
                    ecs_service['lb_type'] = lb_type
                    services.append(ecs_service.copy())

    pprint.pprint(services)
    return services

#
# Create charts in Librato for each ECS service
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

    # get the list of ECS clusters from the configMap
    for config_plugin in configMap['plugins']:
        if config_plugin['name'] == id():
            if debug: log("plugin info found in config file")
            clusters = config_plugin['clusters']

            for cluster in clusters:
                log("processing ECS cluster " + cluster["name"])

                # get the info about all the ECS services on this cluster
                cluster_services = getECSServices(cluster["name"],aws_region,debug)

                # now generate charts for each space configured
                for chart in cluster['charts']:
                    log("creating chart in space " + str(chart["librato_space"]) + " of type " + chart["chart_type"])

                    # Generate charts for each service
                    for cluster_service in cluster_services:
                        log("Processing ECS service for Librato chart " + cluster_service['friendly_name'])

                        chart_status = librato_lb_chart.createLibratoLBChartInSpace(cluster_service['lb_name'],
                                                                                    cluster_service['lb_type'],
                                                                                    cluster_service["friendly_name"],
                                                                                    chart["chart_type"],
                                                                                    chart["librato_space"],
                                                                                    configMap,
                                                                                    debug)

                        if chart_status == 0:
                            log("Chart successfully created/updated in Librato for LB " + cluster_service['lb_name'] + " with name " + cluster_service["friendly_name"])
                        elif chart_status == 1:
                            log("Error creating a chart in Librato for LB " + cluster_service['lb_name'] + " with name " + cluster_service["friendly_name"])
                            plugin_status = 1
                        else:
                            log("Unknown error creating a chart in Librato for LB " + cluster_service['lb_name'] + " with name " + cluster_service["friendly_name"])
                            plugin_status = 1

    return plugin_status

