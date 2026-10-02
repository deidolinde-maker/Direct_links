pipeline {
    agent any

    parameters {
        string(name: 'DIRECT_CAMPAIGN_ID', defaultValue: '109848388', description: 'Campaign ID for targeted Href probe')
        choice(
            name: 'RUN_MODE',
            choices: ['EXPORT_AND_PREPARE', 'DISCOVER_REQUIRED_URLS', 'CHECK_ONLY'],
            description: 'EXPORT_AND_PREPARE обновляет URL-файлы; DISCOVER_REQUIRED_URLS ищет обязательные домены; CHECK_ONLY проверяет check_urls.json'
        )
    }

    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 120, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Export and prepare URL file') {
            when {
                expression { params.RUN_MODE == 'EXPORT_AND_PREPARE' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'YANDEX_DIRECT_LOGIN', variable: 'YANDEX_DIRECT_LOGIN'),
                    string(credentialsId: 'YANDEX_DIRECT_TOKEN', variable: 'YANDEX_DIRECT_TOKEN')
                ]) {
                    sh 'python3 --version'
                    // Merge ad-level URLs with campaign-level URLs from Reports.
                    sh 'python3 export_all_urls.py --date-range LAST_7_DAYS --keep-duplicates'
                    sh 'python3 export_regional_urls.py --date-range LAST_7_DAYS'
                    sh 'python3 build_check_file.py --input urls.json --output check_urls.json'
                    archiveArtifacts artifacts: 'urls.json,regional_urls.json,check_urls.json', fingerprint: true
                }
            }
        }

        stage('Check URL availability') {
            when {
                expression { params.RUN_MODE == 'CHECK_ONLY' }
            }
            steps {
                sh 'test -s check_urls.json'
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    withCredentials([
                        string(credentialsId: 'browser_proxy_creds', variable: 'BROWSER_PROXY_CREDS')
                    ]) {
                        sh 'python3 check_urls.py --input check_urls.json --output availability.json --workers 50 --timeout 15 --retries 3 --retry-delay 0.2 --proxy-creds-env BROWSER_PROXY_CREDS'
                    }
                }
                sh 'rm -rf allure-results && python3 generate_allure.py --input availability.json --output allure-results'
                archiveArtifacts artifacts: 'availability.json,allure-results/**', fingerprint: true
                allure includeProperties: false, jdk: '', results: [[path: 'allure-results']]
            }
        }

        stage('Discover required URLs') {
            when {
                expression { params.RUN_MODE == 'DISCOVER_REQUIRED_URLS' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'YANDEX_DIRECT_LOGIN', variable: 'YANDEX_DIRECT_LOGIN'),
                    string(credentialsId: 'YANDEX_DIRECT_TOKEN', variable: 'YANDEX_DIRECT_TOKEN')
                ]) {
                    sh 'python3 find_required_urls.py --domains-file required_domains.txt --date-range LAST_7_DAYS --output required_urls.json'
                    archiveArtifacts artifacts: 'required_urls.json', fingerprint: true
                }
            }
        }
    }
}
