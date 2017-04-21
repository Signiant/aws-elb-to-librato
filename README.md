# aws-elb-to-librato
Generate error rate charts in Librato from AWS ELB/ALB used by Elastic Beanstalk and ECS services

# Purpose
Using the concept popularized by Google of [error budgets](https://landing.google.com/sre/interview/ben-treynor.html), we'd like to report back to teams who own services what the error rate is of that service.  While AWS cloudwatch provides the raw data for requests and 500s, we need a tool like Librato to transform the data and produce the metrics.  While we are at it, we can use Librato to graph this data too.

We also need it to be dynamic as we add new microservices fairly frequently to AWS ECS.  So the intent of this tool is that it is run on a schedule to continually make sure we have a metric in Librato for all services


# Prerequisites
* You must have a [Librato](https://www.librato.com) subscription.  Go get one now, it's a fantastic tool
* You must have an AWS account
* You must be using either Elastic Beanstalk or ECS services 

# Functionality
The tool is split into the core and plugins.  Currently, there are 2 plugins:

* ECS
  * This plugin queries an ECS cluster and will create a chart for each service that uses a load balancer
* Elastic Beanstalk
  * This plugin queries given elastic beanstalk environments and adds a chart for each environment's load balancer.  It will only create a chart for the current "live" environment where the live environment is defined by a Route53 DNS entry pointing to the environment's load balancer.


# Usage

The easiest way to run the tool is from docker (because docker rocks).  You just pass it a config file and it will do everything from there

```bash
docker pull signiant/aws-elb-to-librato
```

```bash
docker run \
   -v /config/myconfigfile.yaml:/config.yaml \
   signiant/aws-elb-to-librato \
        -c /config.yaml
```

In this example, we use a bindmount to mount in the config file from a local folder to the root directory of the container.  We can then pass the -c argument to the container to have it read the config from /

There is an optional -d flag to the tool which will turn on more debug output.  For example:

```bash
docker run -ti \
   -v /config/myconfigfile.yaml:/config.yaml \
   signiant/aws-elb-to-librato \
        -c /config.yaml \
        -d
```
