#coding: utf-8
import zipfile
import itertools
import logging
import hashlib

from lxml import etree

from . import utils
from . import stylechecker


logger = logging.getLogger(__name__)


class Xray(object):
    """Introspects SPS packages.
    """
    def __init__(self, file):
        """:param file: the full path to a zip file.
        """
        if not zipfile.is_zipfile(file):
            raise ValueError('%s is not a valid zipfile.' % file)

        self._zip_pkg = zipfile.ZipFile(file, 'r')
        self._pkg_names = {}
        self._classify()

    def __del__(self):
        self._cleanup_package_fp()

    def _cleanup_package_fp(self):
        # raises AttributeError if the object have not
        # been initialized properly.
        try:
            self._zip_pkg.close()
        except AttributeError:
            pass

    def _classify(self):
        for fileinfo, filename in zip(self._zip_pkg.infolist(), self._zip_pkg.namelist()):
            # ignore directories and empty files
            if fileinfo.file_size:
                _, ext = filename.rsplit('.', 1)
                ext_node = self._pkg_names.setdefault(ext.lower(), [])
                ext_node.append(filename)

    def get_members(self):
        """Get a list of members.
        """
        members = []
        for names in self._pkg_names.values():
            for name in names:
                members.append(name)

        return members

    def get_classified_members(self):
        """Get a list of members classified by type.
        """
        return dict(self._pkg_names)

    def get_ext(self, ext):
        """
        Get a list os members having ``ext`` as extension. Raises
        ValueError if the archive does not have any members matching
        the extension.
        """
        try:
            return self._pkg_names[ext.lower()]
        except KeyError:
            return []

    def get_fps(self, ext):
        """Get file objects for all members having ``ext`` as extension.
        If ``ext`` is not found in the archive, the iterator is empty.
        """
        filenames = self.get_ext(ext)
        if not filenames:
            raise StopIteration()

        for filename in filenames:
            yield self._zip_pkg.open(filename, 'r')

    def get_fp(self, member):
        """Get file object for member.

        A complete list of members can be checked
        calling get_members().

        :param member: a zip member, e.g. 'foo.xml'
        """
        try:
            return self._zip_pkg.open(member, 'r')
        except KeyError:
            raise ValueError('Missing member %s' % member)

    def checksum(self, algorithm):
        """Checksum the package file using `algorithm`.
        """
        return utils.checksum_file(self._zip_pkg.filename, algorithm)


class SPSPackage(object):
    """SciELO Publishing Schema's article package.

    :param file: The filesystem path to the package.
    """
    def __init__(self, file):
        self.file = file
        self._pack_xray = Xray(file)

    @property
    def xml_fp(self):
        """Returns the file-object to the XML file inside the package.

        Make sure the package has only one XML file, otherwise an
        AttributeError is raised.
        """
        fps = self._pack_xray.get_fps('xml')

        xmls = list(itertools.islice(fps, 2))
        if len(xmls) != 1:
            raise AttributeError('There must be only one xml file inside a package.')

        return xmls[0]

    @property
    def xml_validator(self):
        """stylechecker.XMLValidator instance.
        """
        return utils.setdefault(self, '__xml_validator_instance',
                                lambda: stylechecker.XMLValidator(self.xml_fp))

    def is_valid(self):
        """Performs all package validations sequentialy.
        """
        xml_status = self.xml_validator.validate_all()[0]
        return xml_status

    def list_members_by_type(self):
        """List all package members by type.
        """
        return self._pack_xray.get_classified_members()

    def get_member(self, member_name):
        """Get the file-object of a package member.
        """
        return self._pack_xray.get_fp(member_name)

    get_fp = get_member  # Deprecated

    @property
    def sha1_checksum(self):
        """Checksum package with sha1 algorithm.
        """
        return self._pack_xray.checksum(hashlib.sha1)

    def __repr__(self):
        return '<%s path=%s sha1=%s>' % (self.__class__.__name__,
                                         self.file, self.sha1_checksum)

    def _get_meta(self):
        parsed_xml = etree.parse(self.xml_fp)

        dct_mta = {}
        xml_nodes = {
            "journal_title": "front/journal-meta/journal-title-group/journal-title",
            "journal_eissn": "front/journal-meta/issn[@pub-type='epub']",
            "journal_pissn": "front/journal-meta/issn[@pub-type='ppub']",
            "article_title": "front/article-meta/title-group/article-title",
            "issue_year": "front/article-meta/pub-date/year",
            "issue_volume": "front/article-meta/volume",
            "issue_number": "front/article-meta/issue",
        }

        for node_k, node_v in xml_nodes.items():
            node = parsed_xml.find(node_v)
            dct_mta[node_k] = getattr(node, 'text', None)

        return dct_mta

    @property
    def meta(self):
        """Retrieve journal metadata.
        """
        return utils.setdefault(self, '__meta', self._get_meta)

