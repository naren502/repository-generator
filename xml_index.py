#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#     Copyright (C) 2015 Team Kodi
#     http://kodi.tv
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import gzip
import zipfile
import itertools
import requests
from lxml import etree as ET
from xml.dom import minidom
from argparse import ArgumentParser
from distutils.version import LooseVersion
from datetime import date, timedelta


def fetch_dl_stats():
    date_str = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    filter = ".zip"
    url = "http://mirrors.kodi.tv/stats?downloadstats=%s&filter=%s&format=json&limit=0" \
          % (date_str, filter)

    stats = [(item['Filename'], item['Downloads']) for item in requests.get(url).json()]

    # remove stuff we don't want
    stats = [(path, dls) for path, dls in stats if path.endswith('.zip') and
             path.startswith('/addons/') and '-' in os.path.basename(path)]

    # map to (addon id, downloads) tuple
    stats = [(os.path.basename(path).rsplit("-", 1)[0], int(dls)) for path, dls in stats]

    # reduce to max by addon id
    stats = sorted(stats, key=lambda x: x[0])
    stats = [(key,  max(dls for _, dls in group))
             for key, group in itertools.groupby(stats, lambda x: x[0])]

    return dict(stats)


def split_version(path):
    return os.path.splitext(os.path.basename(path))[0].rsplit('-', 1)


def find_archives(repo_dir):
    for addon_id in os.listdir(repo_dir):
        if os.path.isdir(os.path.join(repo_dir, addon_id)):
            zips = [os.path.join(repo_dir, addon_id, name)
                    for name in os.listdir(os.path.join(repo_dir, addon_id))
                    if os.path.splitext(name)[1] == '.zip' and '-' in name]
            if len(zips) > 0:
                zips.sort(key=lambda _: LooseVersion(split_version(_)[1]), reverse=True)
                yield zips[0]


def create_index(repo_dir, dest, prettify=False):
    dlstats = fetch_dl_stats()

    parser = ET.XMLParser(remove_blank_text=True)
    addons = ET.Element('addons')

    archives = list(find_archives(repo_dir))
    archives.sort(key=lambda _: os.stat(_).st_mtime, reverse=True)

    for archive in archives:
        addon_id, version = split_version(archive)
        with zipfile.ZipFile(archive, 'r') as zf:
            addonxml = zf.read(os.path.join(addon_id, 'addon.xml'))
            tree = ET.fromstring(addonxml, parser)

            metadata_elem = tree.find("./extension[@point='kodi.addon.metadata']")
            if metadata_elem is None:
                metadata_elem = tree.find("./extension[@point='xbmc.addon.metadata']")

            no_things = ['icon.png', 'fanart.jpg', 'changelog.txt']
            for no_thing in no_things:
                if os.path.join(addon_id, no_thing) not in zf.namelist():
                    elem = ET.SubElement(metadata_elem, 'no' + os.path.splitext(no_thing)[0])
                    elem.text = "true"

            elem = ET.SubElement(metadata_elem, 'size')
            elem.text = str(os.path.getsize(archive))

            if addon_id in dlstats:
                elem = ET.SubElement(metadata_elem, 'downloads')
                elem.text = str(dlstats[addon_id])

            addons.append(tree)

    xml = ET.tostring(addons, encoding='utf-8', xml_declaration=True)
    if prettify:
        xml = minidom.parseString(xml).toprettyxml(encoding='utf-8', indent="  ")

    with open(dest, 'wb') as f:
        f.write(xml)

    with gzip.GzipFile(dest + ".gz", 'wb', compresslevel=9, mtime=0) as f:
        f.write(xml)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('-i', '--input', dest='input', required=True, help="Path to the generated repository")
    parser.add_argument('-o', '--output', dest='output', required=True)
    parser.add_argument('-p', '--prettify', dest='prettify', action='store_true', default=False)
    args = parser.parse_args()
    create_index(args.input, args.output, prettify=args.prettify)
