import librato, pprint

def id():
    return "librato_chart"

def log (message):
    print id() + ": " + message

#
# Get the Librato API credentials from the config file
#
def getLibratoCredentials(configMap):
    creds = {'user': '', 'token': ''}

    if 'librato' in configMap and configMap['librato']:
        if 'user' in configMap['librato'] and 'token' in configMap['librato']:
            creds['user'] = configMap['librato']['user']
            creds['token'] = configMap['librato']['token']

    return creds

#
# Checks if a chart with name friendly_name already exists in a given space. Returns the ID if so
#
def doesChartExist(lb_name,space_id,friendly_name,creds,debug):
    chart_id = 0
    found_chart_id = 0
    space = ''

    if debug: log("Checking if a chart exists in space ID " + str(space_id) + " with name " + friendly_name)

    api = librato.connect(creds['user'], creds['token'])

    try:
        space = api.get_space(space_id)
    except Exception as e:
        log("Error retrieving space with ID " + str(space_id) + " from Librato: " + str(e))

    if space:
        charts = space.chart_ids

        for chart_id in charts:
            chart_info = api.get_chart(chart_id, space.id)
            if debug: log("Found a chart with name " + str(chart_info.name))

            if chart_info.name.lower() == friendly_name.lower():
                if debug: log("Match found - chart exists")
                found_chart_id = chart_id
                break

    return found_chart_id

#
# Returns the composite metric struture for an ELB or ALB
#
def getCompositeMetric(lb_name,lb_type):

    composite_metric = ""

    if lb_type == "elb":
        # For ELBs, we need to include te ELB500s in the divisor since the total request count does not include these
        # This is not the case for ALBs

        composite_metric = ("divide(["
                                "zero_fill(sum(["
                                    "series(\"AWS.ELB.HTTPCode_Backend_5XX\",{\"name\":\"" + lb_name + "\"},{function:\"sum\", period:\"60\"}),"
                                    "series(\"AWS.ELB.HTTPCode_ELB_5XX\", {\"name\":\"" + lb_name + "\"}, {function:\"sum\", period:\"60\"})"
                               "])),"
                               "sum(["
                                   "series(\"AWS.ELB.RequestCount\", {\"name\":\"" + lb_name + "\"},{function:\"sum\"}),"
                                   "series(\"AWS.ELB.HTTPCode_ELB_5XX\", {\"name\":\"" + lb_name + "\"}, {function:\"sum\"})"
                               "])"
                            "])"
                           )
    elif lb_type == "alb":
        # ALBs do include the 500s in the total request count so no need to include them in summing the requests
        # the metric names are also different than ELBs

        composite_metric = ("divide(["
                                "zero_fill(sum(["
                                    "series(\"AWS.ApplicationELB.HTTPCode_Target_5XX_Count\",{\"loadbalancer\":\"" + lb_name + "\"},{function:\"sum\", period:\"60\"}),"
                                    "series(\"AWS.ApplicationELB.HTTPCode_ELB_5XX_Count\", {\"loadbalancer\":\"" + lb_name + "\"}, {function:\"sum\", period:\"60\"})"
                               "])),"
                               "sum(["
                                   "series(\"AWS.ApplicationELB.RequestCount\", {\"loadbalancer\":\"" + lb_name + "\"},{function:\"sum\"})"
                               "])"
                            "])"
                           )
    else:
        log("Error. Invalid LB type passed for getCompositeMetric - " + lb_type)

    return composite_metric

#
# Creates a new chart for a load balancer in Librato
#
def createLBChart(lb_name,lb_type,space_id,friendly_name,chart_type,creds,debug):
    retval = 0

    if debug: log("Creating a chart in Librato")

    api = librato.connect(creds['user'], creds['token'])

    try:
        space = api.get_space(space_id)
    except Exception as e:
        log("Error retrieving space with ID " + str(space_id) + " from Librato: " + str(e))
        retval = 1

    librato_metric_stream = {
        "composite": getCompositeMetric(lb_name,lb_type),
        "type": "composite",
        "summary_function": "average",
        "units_short": "% uptime",
        "transform_function": "(1-x)*100",
        "downsample_function": "average"
    }

    if space:
        linechart = api.create_chart(
            friendly_name,
            space,
            type=chart_type,

            streams=[ librato_metric_stream ],
            thresholds=[
                {
                    "operator": "<",
                    "value": 99.95,
                    "type": "red"
                },
                {
                    "operator": "<",
                    "value": 99.97,
                    "type": "yellow"
                }
            ],
            use_last_value=False,
            format='.2f',
            enable_format=True
        )

    return retval

def deleteChart(chart_id,space_id,creds,debug):
    retval = 0

    if debug: log("Deleting a chart in Librato")

    api = librato.connect(creds['user'], creds['token'])

    try:
        space = api.get_space(space_id)
    except Exception as e:
        log("Error retrieving space with ID " + str(space_id) + " from Librato: " + str(e))
        retval = 1

    if space:
        charts = space.chart_ids
        chart = api.get_chart(chart_id, space.id)
        chart.delete()

    return retval

#
# Checks if a given lb name exists in a stream for a given chart id
#
def checkForLBInStream(lb_name,chart_id,space_id,creds,debug):
    retval = False

    if debug: log("Checking for existance LB " + lb_name + " in chart " + str(chart_id))

    api = librato.connect(creds['user'], creds['token'])

    try:
        space = api.get_space(space_id)
    except Exception as e:
        log("Error: Unable to retrieve space with ID " + str(space_id) + " from Librato: " + str(e))
        retval = 1

    if space:
        charts = space.chart_ids
        chart = api.get_chart(chart_id, space.id)

        for stream in chart.streams:
            if stream.composite:
                if debug: log("Composite stream found " + str(stream.composite))
                if lb_name.lower() in stream.composite.lower():
                    if debug: log("Found matching LB in composite metric")
                    retval = True
                    break

    return retval

#
# Main routine to handle creating or replacing the chart in Librato
#
def createLibratoLBChartInSpace(lb_name,lb_type,friendly_name,chart_type,space_id,configMap,debug):
    retval = 1
    chart_id = 0

    log("Creating Librato chart for LB " + lb_name + " in space " + str(space_id))

    librato_creds = getLibratoCredentials(configMap)

    if librato_creds['user'] and librato_creds['token']:
        chart_id = doesChartExist(lb_name,space_id,friendly_name,librato_creds,debug)
        if debug: log("Existing chart id is " + str(chart_id))

        if chart_id != 0:
            if debug: log("Chart already exists in librato with name " + friendly_name + " id " + str(chart_id))

            # Does this pre-existing chart use the same load balancer?  If not, delete and re-add add
            if not checkForLBInStream(lb_name, chart_id, space_id, librato_creds, debug):
                log("Existing chart found with LB " + lb_name + " NOT in composite metric.  Deleting and re-adding")

                # LB not found in pre-existing chart - re-create it
                if  deleteChart(chart_id,space_id,librato_creds,debug) == 0:
                    log("Deleted chart " + str(chart_id) + " from space " + str(space_id))
                    retval = createLBChart(lb_name, lb_type, space_id, friendly_name, chart_type, librato_creds, debug)
                else:
                    log("Error: Unable to delete chart " + str(chart_id) + " from space " + str(space_id))
                    retval = 1
            else:
                retval = 0
        else:
            if debug: log("no pre-existing chart found in Librato - creating")

            retval = createLBChart(lb_name,lb_type,space_id,friendly_name,chart_type,librato_creds,debug)
    else:
        log("Error: No Librato configuration in config file - unable to create charts in Librato")
        retval = 1

    return retval