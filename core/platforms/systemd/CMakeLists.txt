#   BAREOS�� - Backup Archiving REcovery Open Sourced
#
#   Copyright (C) 2017-2017 Bareos GmbH & Co. KG
#
#   This program is Free Software; you can redistribute it and/or
#   modify it under the terms of version three of the GNU Affero General Public
#   License as published by the Free Software Foundation and included
#   in the file LICENSE.
#
#   This program is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#   02110-1301, USA.


MESSAGE( STATUS "CMAKE_CURRENT_LIST_FILE: " ${CMAKE_CURRENT_LIST_FILE} )
MESSAGE(STATUS  "installing systemd files to  ${SYSTEMD_UNITDIR}}")
set(SYSTEMD_TMPFILES ${sysconfdir}/tmpfiles.d)



INSTALL(FILES "bareos-sd.service" DESTINATION ${SYSTEMD_UNITDIR})
INSTALL(FILES "bareos-fd.service" DESTINATION ${SYSTEMD_UNITDIR})
INSTALL(FILES "bareos-dir.service" DESTINATION ${SYSTEMD_UNITDIR})
