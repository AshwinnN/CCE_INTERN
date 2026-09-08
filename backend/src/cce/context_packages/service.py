class ContextPackageService:
    def __init__(self, repository):
        self.repository = repository

    def get_package(self, package_id):
        return self.repository.get_package(package_id)

    def list_packages(self):
        return self.repository.list_packages()

    def get_package_version(self, package_id, version):
        return self.repository.version(package_id, version)

    def active(self, domain_id):
        return self.repository.active(domain_id)
