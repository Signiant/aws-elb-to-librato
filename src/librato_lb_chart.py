import librato

def id():
    return "librato_chart"

def log (message):
    print id() + ": " + message

def createELBChart():
    retval = 0

    return retval

def createALBChart():
    retval = 0

    return retval


def createLibratoLBChartInSpace(lb_name,lb_type,space_id,configMap,debug):
    retval = 0

    log("Creating Librato chart for LB " + lb_name + " in space " + str(space_id))


    return retval