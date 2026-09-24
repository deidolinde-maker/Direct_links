pipeline {
    agent any

    parameters {
        string(name: 'DIRECT_CAMPAIGN_ID', defaultValue: '109848388', description: 'Campaign ID for targeted Href probe')
    }

    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 10, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Run read-only campaigns probe') {
            steps {
                withCredentials([
                    string(credentialsId: 'YANDEX_DIRECT_LOGIN', variable: 'YANDEX_DIRECT_LOGIN'),
                    string(credentialsId: 'YANDEX_DIRECT_TOKEN', variable: 'YANDEX_DIRECT_TOKEN')
                ]) {
                    sh 'python3 --version'
                    // Query campaigns for the client selected by YANDEX_DIRECT_LOGIN.
                    sh 'python3 get_campaigns.py'
                    // Query the requested campaign directly by ID.
                    sh 'python3 get_campaign_urls.py --api-version v501 "${DIRECT_CAMPAIGN_ID:-109848388}" || true'
                    // Use Reports as a diagnostic fallback for campaign type/access.
                    sh 'python3 get_campaign_report.py "${DIRECT_CAMPAIGN_ID:-109848388}"'
                }
            }
        }
    }
}
