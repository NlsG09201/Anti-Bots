targetScope = 'resourceGroup'

@description('Short, lowercase prefix used for Azure resource names.')
@minLength(3)
@maxLength(13)
param namePrefix string = 'streamshield'

@description('Azure region. Defaults to the target resource group region.')
param location string = resourceGroup().location

@description('Full container image reference for the FastAPI API. No image is published by this template.')
param apiImage string

@description('Full container image reference for the background worker. No image is published by this template.')
param workerImage string

@description('PostgreSQL administrator login. Supply through a protected deployment parameter.')
param postgresAdminLogin string

@secure()
@description('PostgreSQL administrator password. Supply from a secret store; never commit a parameter value.')
param postgresAdminPassword string

@description('Azure PostgreSQL Flexible Server SKU name, chosen for the target region and workload.')
param postgresSkuName string

@description('Azure Managed Redis SKU name, chosen for the target region and workload (for example, Balanced_B0).')
param redisSkuName string

@description('Minimum API replicas. Set sizing after workload and cost review.')
@minValue(1)
param apiMinReplicas int = 1

@description('Maximum API replicas. Set sizing after workload and cost review.')
@minValue(1)
param apiMaxReplicas int = 3

@description('Minimum worker replicas. Set sizing after workload and cost review.')
@minValue(1)
param workerMinReplicas int = 1

@description('Maximum worker replicas. Set sizing after workload and cost review.')
@minValue(1)
param workerMaxReplicas int = 1

var suffix = uniqueString(resourceGroup().id)
var logWorkspaceName = '${namePrefix}-logs-${suffix}'
var environmentName = '${namePrefix}-aca-${suffix}'
var postgresName = '${namePrefix}-pg-${suffix}'
var redisName = '${namePrefix}-redis-${suffix}'
var apiName = '${namePrefix}-api-${suffix}'
var workerName = '${namePrefix}-worker-${suffix}'

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: location
  sku: {
    name: postgresSkuName
    tier: 'GeneralPurpose'
  }
  properties: {
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
      tenantId: subscription().tenantId
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Disabled'
    }
    storage: {
      storageSizeGB: 32
    }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'streamshield'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource managedRedis 'Microsoft.Cache/redisEnterprise@2025-04-01' = {
  name: redisName
  location: location
  sku: {
    name: redisSkuName
  }
  properties: {
    encryption: {}
    highAvailability: 'Enabled'
    minimumTlsVersion: '1.2'
  }
}

resource managedRedisDatabase 'Microsoft.Cache/redisEnterprise/databases@2025-04-01' = {
  parent: managedRedis
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    clusteringPolicy: 'OSSCluster'
    evictionPolicy: 'VolatileLRU'
    modules: []
    port: 10000
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: [
            {
              name: 'PORT'
              value: '8000'
            }
            {
              name: 'APP_ENV'
              value: 'production'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
      }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: workerName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: workerImage
          env: [
            {
              name: 'PLATFORM_MONITOR_WORKER'
              value: 'true'
            }
            {
              name: 'PLATFORM_MONITOR_RUN_IN_API'
              value: 'false'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: workerMinReplicas
        maxReplicas: workerMaxReplicas
      }
    }
  }
}

@description('Fully qualified domain name of the PostgreSQL server.')
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName

@description('Azure Managed Redis endpoint. Connect over TLS on port 10000 after private networking and authentication are configured.')
output redisHost string = managedRedis.properties.hostName

@description('Public HTTPS URL for the API ingress.')
output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
