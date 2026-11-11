<!-- ===========================================================================
    File: incident_in_7.3.xsl

    Andre L'Hoir - Ariste Mathy, 2025-05-21
    Vittorio Reina JRC,          2018-10-31
  
 	Walter Schnell, for Optimal Systems, 2009-11-16
	Projekt MEDDEV3 for BfArM

	the xslt-in transformation that is used in the MEDDEV PDF form
	basically, these are the things that Acrobat cannot do in LiveCycle Designer:
	- fill multiple tags from one form field

	ideas:
	set to UTF-16 later
 
 	history (incomplete):
	7.3.1	2026-05-06	AL  SB-11154 - Latest version delivered
	7.3.1   2025-10-15  AL  SB-10781 Align business rules for Turkey in section 1.3.3
	7.3.1   2025-05-21  AL  SB-10434 Align country code list among PDF, XSL and XSD 
    7.3.1   2025-02-04  AL  Latest version: SANCOBO-10332 
    7.2.1	2020-03-03  VR
	7.0 	2018-10-31  VR
	3.2		2013-06-05	WS	HR in EU; 
	3.1		2012-02-22	WS	turkey like EU; countries doubles reimport error corrected;
	3.0		2011-09-27	WS	use xsl:if; 

=========================================================================== -->

<xsl:stylesheet version="2.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="xml" indent="yes" encoding="UTF-8" /> 

<!-- triple the contact info so it will be interpreted = chosen = switched by the XSD according to the statusReporter field -->

<xsl:template match="/incident/admin_info/contact_info/reporterAR">
	<reporterMfr>
		<xsl:apply-templates/>
	</reporterMfr>
</xsl:template>

<xsl:template match="/incident/admin_info/contact_info/reporterOther">
	<reporterMfr>
		<xsl:apply-templates/>
	</reporterMfr>
</xsl:template>

<xsl:template match="/incident/device_info/distribution">
	<distribution>
		<xsl:variable name="sAT">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'AT'">AT</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sBE">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'BE'">BE</xsl:if>
			</xsl:for-each>
		</xsl:variable>
		
		<xsl:variable name="sBG">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'BG'">BG</xsl:if>
			</xsl:for-each>
		</xsl:variable>
		
		<xsl:variable name="sCH">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'CH'">CH</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sCY">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'CY'">CY</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sCZ">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'CZ'">CZ</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sDE">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'DE'">DE</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sDK">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'DK'">DK</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sEE">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'EE'">EE</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sES">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'ES'">ES</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sFI">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'FI'">FI</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sFR">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'FR'">FR</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sXI">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'XI'">XI</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sGR">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'GR'">GR</xsl:if>
			</xsl:for-each>
		</xsl:variable>
		
		<xsl:variable name="sHU">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'HU'">HU</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sIE">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'IE'">IE</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sIS">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'IS'">IS</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sIT">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'IT'">IT</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sLI">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'LI'">LI</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sLT">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'LT'">LT</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sLU">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'LU'">LU</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sLV">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'LV'">LV</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sMT">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'MT'">MT</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sNL">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'NL'">NL</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sNO">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'NO'">NO</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sPL">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'PL'">PL</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sPT">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'PT'">PT</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sRO">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'RO'">RO</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sSE">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'SE'">SE</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sSI">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'SI'">SI</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sSK">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'SK'">SK</xsl:if>
			</xsl:for-each>
		</xsl:variable>

		<xsl:variable name="sTR">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'TR'">TR</xsl:if>
			</xsl:for-each>
		</xsl:variable>
	  
		<xsl:variable name="sHR">
			<xsl:for-each select="distributionEEA">
				<xsl:variable name="value" select="." />
				<xsl:if test="$value = 'HR'">HR</xsl:if>
			</xsl:for-each>
		</xsl:variable>
		
		<distributionEEA><xsl:value-of select="$sAT"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sBE"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sBG"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sCH"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sCY"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sCZ"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sDE"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sDK"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sEE"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sES"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sFI"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sFR"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sXI"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sGR"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sHR"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sHU"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sIE"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sIS"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sIT"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sLI"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sLT"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sLU"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sLV"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sMT"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sNL"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sNO"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sPL"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sPT"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sRO"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sSE"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sSI"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sSK"/></distributionEEA>
		<distributionEEA><xsl:value-of select="$sTR"/></distributionEEA>
		
		<distribution_all><xsl:value-of select="distribution_all"/></distribution_all>
		<otherCountries><xsl:value-of select="otherCountries"/></otherCountries>
	</distribution>
</xsl:template>

<xsl:template match="incident/admin_info/ncaRefMultiDevLI"/>
<xsl:template match="incident/admin_info/eudamedRefMultiDevLI"/>
<xsl:template match="incident/admin_info/mfrRefMultiDevLI"/>
<xsl:template match="incident/admin_info/ncaRefFSCALI"/>
<xsl:template match="incident/admin_info/eudamedRefFSCALI"/>
<xsl:template match="incident/admin_info/mfrRefFSCALI"/>
<xsl:template match="incident/admin_info/psrIdLI"/>
<xsl:template match="incident/admin_info/pmcfpmpfIdLI"/>
<xsl:template match="incident/device_info/distribution/otherCountriesLI"/>

<!-- indentity transformation = keep output like input tree -->

<xsl:template match="node()|@*">
	<xsl:copy>
		<xsl:apply-templates select="node()|@*"/>
	</xsl:copy>
</xsl:template>

</xsl:stylesheet>

